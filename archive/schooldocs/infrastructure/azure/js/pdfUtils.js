const fileType = require('file-type');
const pdfParse = require('pdf-parse');
const { execFile } = require('child_process');
const fs = require('fs').promises;
const crypto = require('crypto');
const { v4: uuidv4 } = require('uuid');
const path = require('path');
const os = require('os');

async function validatePdfFile(filePath) {
  const buffer = await fs.readFile(filePath);
  const type = await fileType.fromBuffer(buffer);
  if (!type || type.mime !== 'application/pdf') {
    throw new Error('유효한 PDF 파일이 아닙니다.');
  }
  const data = await pdfParse(buffer);
  if (data.numpages > 5) {
    throw new Error('5페이지 이하의 인증서만 업로드 가능합니다.');
  }
  const hash = crypto.createHash('sha256').update(buffer).digest('hex');
  return { hash, pageCount: data.numpages, buffer };
}

async function convertPdfToJpeg(pdfPath) {
  const tempJpeg = path.join(os.tmpdir(), `${uuidv4()}.jpg`);

  return new Promise((resolve, reject) => {
    execFile('gs', [
      '-dNOPAUSE',
      '-dBATCH',
      '-dSAFER',
      '-sDEVICE=jpeg',
      '-dJPEGQ=85',
      '-r100',
      '-dTextAlphaBits=4',
      '-dGraphicsAlphaBits=4',
      '-dFirstPage=1',
      '-dLastPage=1',
      `-sOutputFile=${tempJpeg}`,
      pdfPath
    ], { timeout: 15000 }, (err) => {
      if (err) reject(new Error(`Ghostscript 변환 실패: ${err.message}`));
      else resolve(tempJpeg);
    });
  });
}

module.exports = { validatePdfFile, convertPdfToJpeg };