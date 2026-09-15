const express = require('express');
const multer = require('multer');
const pdfParse = require('pdf-parse');
const fs = require('fs').promises;
const crypto = require('crypto');
const router = express.Router();

const { validatePdfFile, convertPdfToJpeg } = require('../utils/pdfUtils');
const { callAIWithRateLimit } = require('../utils/aiUtils');
const { uploadToBlob } = require('../utils/storage');
const { getCosmosContainer } = require('../utils/cosmos');
const { createAuditEntry } = require('../utils/auditTrail');
const { getCohortId } = require('../utils/documentTypes');
const { encrypt, hashPersonId } = require('../utils/cryptoUtils');

// OOM 방지를 위한 디스크 임시 저장
const upload = multer({
  dest: '/tmp/uploads/',
  limits: { fileSize: 10 * 1024 * 1024 }
}).fields([
  { name: 'pdf', maxCount: 1 },
  { name: 'personId' },
  { name: 'name' },
  { name: 'birthdate' },
  { name: 'submittedYear' },
  { name: 'documentType' }
]);

async function parseByRule(buffer) {
  const text = (await pdfParse(buffer)).text;
  // TODO: 규칙 기반 파싱 로직 구현
  return { success: false };
}

router.post('/submit', async (req, res) => {
  let pdfPath = null;
  let jpegPath = null;

  try {
    const { personId, name, birthdate, submittedYear, documentType } = req.body;
    const pdfFile = req.files['pdf']?.[0];
    if (!pdfFile) return res.status(400).json({ error: 'PDF 파일이 필요합니다.' });
    if (!personId || !name || !birthdate || !submittedYear || !documentType) {
      return res.status(400).json({ error: '필수 항목 누락' });
    }

    pdfPath = pdfFile.path;
    const { buffer, hash, pageCount } = await validatePdfFile(pdfPath);
    const personKey = await hashPersonId(name, birthdate);
    const cohortId = getCohortId(documentType, submittedYear);
    const fileHash = crypto.createHash('sha256').update(buffer).digest('hex');
    const recordId = `${cohortId}:${personKey}`;

    const container = getCosmosContainer('records');

    // 기존 제출물 확인 (Point Read)
    let existingRecord = null;
    try {
      const { resource } = await container.item(recordId, cohortId).read();
      existingRecord = resource;
    } catch (err) {
      if (err.code !== 404) throw err;
    }

    // 규칙 기반 파싱
    let parsed = null;
    let status = 'pending';
    let aiConfidence = null;

    const parsedData = await parseByRule(buffer);
    if (parsedData.success) {
      parsed = { isParsed: true, source: 'rule', ...parsedData.data };
    } else {
      const aiResult = await callAIWithRateLimit(buffer, hash);
      if (aiResult.success) {
        parsed = { isParsed: true, source: 'gpt-4o-mini', ...aiResult.data };
        status = 'pending_ai';
        aiConfidence = aiResult.confidence;
      } else {
        parsed = { isParsed: false, failedFields: aiResult.failedFields || ['name', 'year'] };
        status = 'unknown';
      }
    }

    // JPEG 변환
    jpegPath = await convertPdfToJpeg(pdfPath);

    // Blob Storage 업로드
    const baseBlobName = `${documentType}/${submittedYear}/${personKey}/${recordId}`;
    const originalPdfBlobName = await uploadToBlob(pdfPath, `${baseBlobName}.pdf`);
    const thumbnailBlobName = await uploadToBlob(jpegPath, `${baseBlobName}.jpg`);

    const encryptedName = await encrypt(name);

    const recordData = {
      id: recordId,
      cohortId,
      personKey,
      type: 'submission',
      status,
      fileHash,
      thumbnailPath: thumbnailBlobName,
      originalPdfPath: originalPdfBlobName,
      parsed,
      aiConfidence,
      nameEncrypted: encryptedName,
      submittedAt: new Date().toISOString(),
      updatedAt: new Date().toISOString(),
      auditTrail: [
        ...(existingRecord?.auditTrail || []),
        createAuditEntry('SUBMIT', 'system', { fileHash, overwrite: !!existingRecord })
      ]
    };

    await container.items.upsert(recordData);

    res.status(201).json({
      message: '제출 완료',
      recordId: recordData.id,
      status,
      overwritten: !!existingRecord
    });

  } catch (err) {
    console.error(err);
    res.status(500).json({ error: '서버 오류' });
  } finally {
    if (pdfPath) await fs.unlink(pdfPath).catch(() => {});
    if (jpegPath) await fs.unlink(jpegPath).catch(() => {});
  }
});

module.exports = router;
