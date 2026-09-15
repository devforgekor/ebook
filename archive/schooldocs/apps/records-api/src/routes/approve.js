const express = require('express');
const router = express.Router();
const { getCosmosContainer } = require('../utils/cosmos');
const { createAuditEntry } = require('../utils/auditTrail');
const { getUserFromAuthHeader, getUserGroups } = require('../utils/auth'); // 공통 유틸 분리 가정
// 간단하게 위해 여기서는 위 pending.js와 동일한 헬퍼를 포함하겠습니다.

// (auth 헬퍼 함수 생략 - pending.js와 동일)
function getUserFromAuthHeader(req) { /* ... */ }
function getUserGroups(req) { /* ... */ }

async function requireAuth(req, res, next) {
  const user = getUserFromAuthHeader(req);
  if (!user) return res.status(401).json({ error: '인증 필요' });
  const groups = getUserGroups(req);
  const allowed = [process.env.SUPER_ADMIN_GROUP_ID, process.env.ADMIN_GROUP_ID];
  if (!groups.some(g => allowed.includes(g))) {
    return res.status(403).json({ error: '권한 없음' });
  }
  req.user = user;
  next();
}

// POST /api/manage/approve
// body: { recordId: "...", cohortId: "...", action: "approve" | "reject", reason?: string }
router.post('/approve', requireAuth, async (req, res) => {
  try {
    const { recordId, cohortId, action, reason } = req.body;
    if (!recordId || !cohortId || !action) {
      return res.status(400).json({ error: 'recordId, cohortId, action은 필수입니다.' });
    }
    if (action !== 'approve' && action !== 'reject') {
      return res.status(400).json({ error: 'action은 approve 또는 reject이어야 합니다.' });
    }

    const container = getCosmosContainer('records');
    const { resource: doc } = await container.item(recordId, cohortId).read();
    if (!doc || doc.type !== 'submission') {
      return res.status(404).json({ error: '제출 기록을 찾을 수 없습니다.' });
    }

    const newStatus = action === 'approve' ? 'approved' : 'rejected';
    const auditEntry = createAuditEntry(
      action.toUpperCase(),
      req.user.email,
      { reason: reason || '', previousStatus: doc.status }
    );

    const patchOperations = [
      { op: 'replace', path: '/status', value: newStatus },
      { op: 'add', path: '/auditTrail/-', value: auditEntry },
      { op: 'replace', path: '/updatedAt', value: new Date().toISOString() }
    ];

    // 거절된 경우 TTL 설정 (24시간 후 자동 삭제) - 기수 마감 시 일괄 처리도 가능하나 여기서 즉시 적용
    if (action === 'reject') {
      patchOperations.push({ op: 'add', path: '/ttl', value: 86400 });
    }

    await container.item(recordId, cohortId).patch(patchOperations);

    res.json({
      message: `처리 완료: ${newStatus}`,
      recordId,
      status: newStatus
    });
  } catch (err) {
    console.error('approve error:', err);
    res.status(500).json({ error: '서버 오류' });
  }
});

module.exports = router;
