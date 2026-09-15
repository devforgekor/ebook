const express = require('express');
const router = express.Router();
const { getCosmosContainer } = require('../utils/cosmos');

// 인증 미들웨어 (super-admin만 접근 가능)
async function requireSuperAdmin(req, res, next) {
  const header = req.headers['x-ms-client-principal'];
  if (!header) return res.status(401).json({ error: '인증 필요' });
  try {
    const decoded = Buffer.from(header, 'base64').toString('ascii');
    const principal = JSON.parse(decoded);
    const groups = principal.claims?.filter(c => c.typ === 'groups').map(c => c.val) || [];
    const superAdminGroupId = process.env.SUPER_ADMIN_GROUP_ID;
    if (!groups.includes(superAdminGroupId)) {
      return res.status(403).json({ error: 'Super-admin 권한 필요' });
    }
    next();
  } catch {
    return res.status(401).json({ error: '인증 오류' });
  }
}

// GET /api/manage/cohorts - 모든 기수 목록
router.get('/cohorts', requireSuperAdmin, async (req, res) => {
  try {
    const container = getCosmosContainer('registry');
    const querySpec = {
      query: `SELECT * FROM c WHERE c.type = 'cohort' ORDER BY c.createdAt DESC`
    };
    const { resources } = await container.items.query(querySpec).fetchAll();
    res.json(resources);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: '서버 오류' });
  }
});

// POST /api/manage/cohorts - 새 기수 생성
router.post('/cohorts', requireSuperAdmin, async (req, res) => {
  try {
    const { cohortId, displayName, deadline } = req.body;
    if (!cohortId) {
      return res.status(400).json({ error: 'cohortId 필수' });
    }

    const container = getCosmosContainer('registry');
    const id = `cohort_${cohortId}`;
    const newCohort = {
      id,
      cohortId,
      type: 'cohort',
      displayName: displayName || cohortId,
      active: true,
      createdAt: new Date().toISOString(),
      deadline: deadline || null
    };

    await container.items.create(newCohort);
    res.status(201).json(newCohort);
  } catch (err) {
    if (err.code === 409) {
      return res.status(409).json({ error: '이미 존재하는 기수입니다.' });
    }
    console.error(err);
    res.status(500).json({ error: '서버 오류' });
  }
});

module.exports = router;
