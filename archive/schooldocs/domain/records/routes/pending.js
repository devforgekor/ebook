const express = require('express');
const router = express.Router();
const { getCosmosContainer } = require('../../../infrastructure/azure/js/cosmos');
const { decrypt } = require('../../../core/js/utils/cryptoUtils');

// Easy Auth 헤더에서 사용자 정보 추출
function getUserFromAuthHeader(req) {
  const header = req.headers['x-ms-client-principal'];
  if (!header) return null;
  try {
    const decoded = Buffer.from(header, 'base64').toString('ascii');
    const principal = JSON.parse(decoded);
    const email = principal.claims?.find(c => c.typ === 'email')?.val;
    const name = principal.claims?.find(c => c.typ === 'name')?.val;
    const objectId = principal.claims?.find(c => c.typ === 'http://schemas.microsoft.com/identity/claims/objectidentifier')?.val;
    return { email, name, objectId };
  } catch {
    return null;
  }
}

// 그룹 멤버십 확인 (헤더에 포함된 그룹 목록)
function getUserGroups(req) {
  const header = req.headers['x-ms-client-principal'];
  if (!header) return [];
  try {
    const decoded = Buffer.from(header, 'base64').toString('ascii');
    const principal = JSON.parse(decoded);
    return principal.claims
      ?.filter(c => c.typ === 'groups')
      .map(c => c.val) || [];
  } catch {
    return [];
  }
}

// 권한 확인 미들웨어 (admin 이상)
async function requireAuth(req, res, next) {
  const user = getUserFromAuthHeader(req);
  if (!user) {
    return res.status(401).json({ error: '인증이 필요합니다.' });
  }

  const groups = getUserGroups(req);
  const superAdminGroupId = process.env.SUPER_ADMIN_GROUP_ID;
  const adminGroupId = process.env.ADMIN_GROUP_ID;

  // super-admin 또는 admin 그룹에 속하는지 확인
  if (groups.includes(superAdminGroupId) || groups.includes(adminGroupId)) {
    req.user = user;
    req.userGroups = groups;
    return next();
  }

  return res.status(403).json({ error: '권한이 없습니다.' });
}

// GET /api/manage/pending?cohortId=...
router.get('/pending', requireAuth, async (req, res) => {
  try {
    const { cohortId } = req.query;
    if (!cohortId) {
      return res.status(400).json({ error: 'cohortId 쿼리 파라미터가 필요합니다.' });
    }

    const container = getCosmosContainer('records');
    const querySpec = {
      query: `SELECT * FROM c WHERE c.cohortId = @cohortId AND c.type = 'submission' AND (c.status = 'pending' OR c.status = 'pending_ai')`,
      parameters: [{ name: '@cohortId', value: cohortId }]
    };

    const { resources } = await container.items.query(querySpec).fetchAll();

    // 복호화하여 반환할 데이터 구성
    const pendingList = await Promise.all(resources.map(async (item) => {
      let decryptedName = null;
      try {
        decryptedName = await decrypt(item.nameEncrypted);
      } catch (e) {
        decryptedName = '[복호화 오류]';
      }
      return {
        id: item.id,
        personKey: item.personKey,
        name: decryptedName,
        status: item.status,
        submittedAt: item.submittedAt,
        parsed: item.parsed,
        aiConfidence: item.aiConfidence,
        hasThumbnail: !!item.thumbnailPath
      };
    }));

    res.json({
      cohortId,
      count: pendingList.length,
      items: pendingList
    });
  } catch (err) {
    console.error('pending list error:', err);
    res.status(500).json({ error: '서버 오류' });
  }
});

module.exports = router;
