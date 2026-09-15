const express = require('express');
const router = express.Router();
const { getCosmosContainer } = require('../utils/cosmos');
const { generateSasUrl } = require('../utils/storage');

router.get('/view/:recordId', async (req, res) => {
  try {
    const recordId = req.params.recordId;
    // cohortId는 recordId에서 추출 (예: "safety_2024:abc...")
    const cohortId = recordId.split(':')[0];

    const container = getCosmosContainer('records');
    const { resource } = await container.item(recordId, cohortId).read();

    if (!resource || !resource.thumbnailPath) {
      return res.status(404).json({ error: '이미지를 찾을 수 없습니다.' });
    }

    const sasUrl = await generateSasUrl(resource.thumbnailPath);
    res.redirect(302, sasUrl);
  } catch (err) {
    if (err.code === 404) {
      return res.status(404).json({ error: '이미지를 찾을 수 없습니다.' });
    }
    console.error(err);
    res.status(500).json({ error: '서버 오류' });
  }
});

module.exports = router;
