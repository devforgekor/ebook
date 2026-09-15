const express = require('express');
const multer = require('multer');
const csv = require('csv-parser');
const fs = require('fs').promises;
const { Readable } = require('stream');
const router = express.Router();
const { getCosmosContainer } = require('../utils/cosmos');
const { encrypt, hashPersonId } = require('../utils/cryptoUtils');
const { getCohortId } = require('../utils/documentTypes');

const upload = multer({ dest: '/tmp/members/' });

// 인증 미들웨어 (admin 이상)
async function requireAuth(req, res, next) {
  const header = req.headers['x-ms-client-principal'];
  if (!header) return res.status(401).json({ error: '인증 필요' });
  try {
    const decoded = Buffer.from(header, 'base64').toString('ascii');
    const principal = JSON.parse(decoded);
    const groups = principal.claims?.filter(c => c.typ === 'groups').map(c => c.val) || [];
    const allowed = [process.env.SUPER_ADMIN_GROUP_ID, process.env.ADMIN_GROUP_ID];
    if (!groups.some(g => allowed.includes(g))) {
      return res.status(403).json({ error: '권한 없음' });
    }
    next();
  } catch {
    return res.status(401).json({ error: '인증 오류' });
  }
}

// POST /api/manage/upload-members
// form-data: csv 파일, fields: cohortId, documentType, submittedYear
router.post('/upload-members', requireAuth, upload.single('csv'), async (req, res) => {
  const filePath = req.file?.path;
  if (!filePath) {
    return res.status(400).json({ error: 'CSV 파일이 필요합니다.' });
  }

  const { cohortId, documentType, submittedYear } = req.body;
  if (!cohortId || !documentType || !submittedYear) {
    await fs.unlink(filePath).catch(() => {});
    return res.status(400).json({ error: 'cohortId, documentType, submittedYear 필수' });
  }

  // 기수 존재 여부 확인
  const registryContainer = getCosmosContainer('registry');
  try {
    await registryContainer.item(`cohort_${cohortId}`, cohortId).read();
  } catch (err) {
    await fs.unlink(filePath).catch(() => {});
    if (err.code === 404) return res.status(404).json({ error: '존재하지 않는 기수입니다.' });
    throw err;
  }

  const container = getCosmosContainer('records');
  const results = [];
  const errors = [];
  let processed = 0;

  try {
    const fileContent = await fs.readFile(filePath, 'utf8');
    const stream = Readable.from(fileContent);

    await new Promise((resolve, reject) => {
      stream
        .pipe(csv({ headers: ['name', 'birthdate', 'personId'] })) // 예시 컬럼
        .on('data', async (row) => {
          // 스트림 중단 없이 처리하기 위해 Promise를 수집
          results.push((async () => {
            try {
              const { name, birthdate, personId } = row;
              if (!name || !birthdate || !personId) {
                errors.push({ row, error: '필수 컬럼 누락' });
                return;
              }

              const personKey = await hashPersonId(name, birthdate);
              const encryptedName = await encrypt(name);
              const memberId = `${cohortId}_member_${personId}`;

              const memberDoc = {
                id: memberId,
                cohortId,
                personId,
                personKey,
                type: 'member',
                nameEncrypted: encryptedName,
                birthdateHash: personKey, // 생년월일 해시는 personKey와 동일
                documentType,
                submittedYear,
                createdAt: new Date().toISOString()
              };

              await container.items.upsert(memberDoc);
              processed++;
            } catch (e) {
              errors.push({ row, error: e.message });
            }
          })());
        })
        .on('end', async () => {
          await Promise.all(results);
          resolve();
        })
        .on('error', reject);
    });

    await fs.unlink(filePath).catch(() => {});

    res.json({
      message: '명단 업로드 완료',
      processed,
      errors: errors.length > 0 ? errors : undefined
    });
  } catch (err) {
    await fs.unlink(filePath).catch(() => {});
    console.error(err);
    res.status(500).json({ error: '서버 오류' });
  }
});

module.exports = router;
