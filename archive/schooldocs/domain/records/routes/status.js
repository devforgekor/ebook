const express = require('express');
const router = express.Router();
const { getCosmosContainer } = require('../../../infrastructure/azure/js/cosmos');
const { decrypt, hashPersonId } = require('../../../core/js/utils/cryptoUtils');
const { getCohortId } = require('../models/documentTypes');

router.post('/status', async (req, res) => {
  try {
    const { name, birthdate, documentType, submittedYear } = req.body;
    if (!name || !birthdate || !documentType || !submittedYear) {
      return res.status(400).json({ error: '필수 항목 누락' });
    }

    const personKey = await hashPersonId(name, birthdate);
    const cohortId = getCohortId(documentType, submittedYear);
    const recordId = `${cohortId}:${personKey}`;

    const container = getCosmosContainer('records');
    const { resource } = await container.item(recordId, cohortId).read();

    if (!resource || resource.type !== 'submission') {
      return res.status(404).json({ message: '제출 내역 없음' });
    }

    res.json({
      id: resource.id,
      name: await decrypt(resource.nameEncrypted),
      status: resource.status,
      submittedAt: resource.submittedAt,
      cohortId: resource.cohortId,
      hasImage: !!resource.thumbnailPath
    });
  } catch (err) {
    if (err.code === 404) {
      return res.status(404).json({ message: '제출 내역 없음' });
    }
    console.error(err);
    res.status(500).json({ error: '서버 오류' });
  }
});

module.exports = router;
