const express = require('express');
const router = express.Router();
const { getCosmosContainer } = require('../utils/cosmos');
const { createAuditEntry } = require('../utils/auditTrail');

// super-admin 인증 미들웨어 (cohorts.js와 동일)
async function requireSuperAdmin(req, res, next) {
  const header = req.headers['x-ms-client-principal'];
  if (!header) return res.status(401).json({ error: '인증 필요' });
  try {
    const decoded = Buffer.from(header, 'base64').toString('ascii');
    const principal = JSON.parse(decoded);
    const groups = principal.claims?.filter(c => c.typ === 'groups').map(c => c.val) || [];
    if (!groups.includes(process.env.SUPER_ADMIN_GROUP_ID)) {
      return res.status(403).json({ error: 'Super-admin 권한 필요' });
    }
    next();
  } catch {
    return res.status(401).json({ error: '인증 오류' });
  }
}

// PATCH /api/manage/close-cohort
// body: { cohortId: "..." }
router.patch('/close-cohort', requireSuperAdmin, async (req, res) => {
  try {
    const { cohortId } = req.body;
    if (!cohortId) {
      return res.status(400).json({ error: 'cohortId 필수' });
    }

    const registryContainer = getCosmosContainer('registry');
    const recordsContainer = getCosmosContainer('records');

    // 1. registry에서 기수 비활성화
    const cohortDocId = `cohort_${cohortId}`;
    const { resource: cohort } = await registryContainer.item(cohortDocId, cohortId).read();
    if (!cohort) {
      return res.status(404).json({ error: '기수를 찾을 수 없습니다.' });
    }

    await registryContainer.item(cohortDocId, cohortId).patch([
      { op: 'replace', path: '/active', value: false },
      { op: 'replace', path: '/closedAt', value: new Date().toISOString() }
    ]);

    // 2. records에서 해당 기수의 거절(rejected) 문서에 TTL 설정 (24시간 후 삭제)
    const querySpec = {
      query: `SELECT * FROM c WHERE c.cohortId = @cohortId AND c.type = 'submission' AND c.status = 'rejected'`,
      parameters: [{ name: '@cohortId', value: cohortId }]
    };
    const { resources: rejectedDocs } = await recordsContainer.items.query(querySpec).fetchAll();

    const patchOps = rejectedDocs.map(doc => ({
      operation: 'Patch',
      resourceId: doc.id,
      partitionKey: cohortId,
      operations: [
        { op: 'add', path: '/ttl', value: 86400 },
        { op: 'add', path: '/auditTrail/-', value: createAuditEntry('COHORT_CLOSED', 'system', { note: '기수 마감으로 삭제 예정' }) }
      ]
    }));

    // 병렬 처리 (최대 100건 가정)
    await Promise.all(patchOps.map(op => recordsContainer.item(op.resourceId, op.partitionKey).patch(op.operations)));

    res.json({
      message: '기수 마감 처리 완료',
      cohortId,
      rejectedCount: rejectedDocs.length
    });
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: '서버 오류' });
  }
});

module.exports = router;
