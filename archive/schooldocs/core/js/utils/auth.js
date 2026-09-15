// apps/records-api/src/utils/auth.js
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

function getUserGroups(req) {
  const header = req.headers['x-ms-client-principal'];
  if (!header) return [];
  try {
    const decoded = Buffer.from(header, 'base64').toString('ascii');
    const principal = JSON.parse(decoded);
    return principal.claims?.filter(c => c.typ === 'groups').map(c => c.val) || [];
  } catch {
    return [];
  }
}

function requireAuth(requiredRoles = ['admin', 'super-admin']) {
  return async (req, res, next) => {
    const user = getUserFromAuthHeader(req);
    if (!user) return res.status(401).json({ error: '인증 필요' });

    const groups = getUserGroups(req);
    const superAdminGroupId = process.env.SUPER_ADMIN_GROUP_ID;
    const adminGroupId = process.env.ADMIN_GROUP_ID;
    const subAdminGroupId = process.env.SUB_ADMIN_GROUP_ID;

    const roleMap = {
      'super-admin': superAdminGroupId,
      'admin': adminGroupId,
      'sub-admin': subAdminGroupId
    };

    const hasRole = requiredRoles.some(role => groups.includes(roleMap[role]));
    if (!hasRole) return res.status(403).json({ error: '권한 없음' });

    req.user = user;
    req.userGroups = groups;
    next();
  };
}

module.exports = { getUserFromAuthHeader, getUserGroups, requireAuth };
