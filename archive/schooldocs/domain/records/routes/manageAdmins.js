const express = require('express');
const router = express.Router();
const { getCosmosContainer } = require('../../../infrastructure/azure/js/cosmos');

// super-admin 인증
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

// GET /api/manage/admins - 관리자 목록 조회
router.get('/admins', requireSuperAdmin, async (req, res) => {
  try {
    const container = getCosmosContainer('admins');
    const { resources } = await container.items.readAll().fetchAll();
    // 민감 정보 제외
    const safeList = resources.map(a => ({
      id: a.id,
      email: a.email,
      name: a.name,
      role: a.role,
      createdAt: a.createdAt
    }));
    res.json(safeList);
  } catch (err) {
    console.error(err);
    res.status(500).json({ error: '서버 오류' });
  }
});

// POST /api/manage/admins - 새 관리자 추가
router.post('/admins', requireSuperAdmin, async (req, res) => {
  try {
    const { email, name, role } = req.body;
    if (!email || !role) {
      return res.status(400).json({ error: 'email, role 필수' });
    }
    if (!['super-admin', 'admin', 'sub-admin'].includes(role)) {
      return res.status(400).json({ error: 'role은 super-admin, admin, sub-admin 중 하나여야 합니다.' });
    }

    const container = getCosmosContainer('admins');
    const id = `admin_${email.replace(/[^a-zA-Z0-9]/g, '_')}`;

    const newAdmin = {
      id,
      email,
      name: name || email,
      role,
      createdAt: new Date().toISOString(),
      type: 'admin'
    };

    await container.items.create(newAdmin);
    res.status(201).json({ message: '관리자 추가됨', admin: { email, name: newAdmin.name, role } });
  } catch (err) {
    if (err.code === 409) {
      return res.status(409).json({ error: '이미 등록된 이메일입니다.' });
    }
    console.error(err);
    res.status(500).json({ error: '서버 오류' });
  }
});

// DELETE /api/manage/admins/:email - 관리자 삭제
router.delete('/admins/:email', requireSuperAdmin, async (req, res) => {
  try {
    const email = decodeURIComponent(req.params.email);
    const container = getCosmosContainer('admins');
    const id = `admin_${email.replace(/[^a-zA-Z0-9]/g, '_')}`;

    await container.item(id, id).delete();
    res.json({ message: '관리자 삭제됨', email });
  } catch (err) {
    if (err.code === 404) {
      return res.status(404).json({ error: '관리자를 찾을 수 없습니다.' });
    }
    console.error(err);
    res.status(500).json({ error: '서버 오류' });
  }
});

module.exports = router;
