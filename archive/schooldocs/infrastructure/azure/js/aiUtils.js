const { OpenAIClient } = require("@azure/openai");
const { DefaultAzureCredential } = require("@azure/identity");
const pdfParse = require('pdf-parse');
const { getCosmosContainer } = require('./cosmos');

const endpoint = process.env.AZURE_OPENAI_ENDPOINT;
const deploymentName = process.env.AZURE_OPENAI_DEPLOYMENT_NAME || 'gpt-4o-mini';
const credential = new DefaultAzureCredential();
const client = new OpenAIClient(endpoint, credential);

/**
 * 파일 해시 기반 Rate Limit 확인 (동일 PDF 1시간 내 1회만 AI 호출)
 */
async function checkAIRateLimit(fileHash) {
  const container = getCosmosContainer('records');
  const docId = `ai_limit_${fileHash}`;
  try {
    await container.items.create({
      id: docId,
      cohortId: 'system',
      type: 'rate_limit',
      ttl: 3600 // 1시간 후 자동 삭제
    });
    return true;
  } catch (err) {
    if (err.code === 409) return false; // 이미 존재 → rate limited
    throw err;
  }
}

/**
 * 규칙 기반 파싱 (정규식)
 */
function parseByRule(text) {
  const patterns = {
    name: [
      /성명\s*[:：]\s*([^\n\r]+)/,
      /이름\s*[:：]\s*([^\n\r]+)/,
      /수강생\s*[:：]\s*([^\n\r]+)/
    ],
    year: [
      /이수\s*(연도|년도)\s*[:：]\s*(\d{4})/,
      /수료\s*(연도|년도)\s*[:：]\s*(\d{4})/,
      /교육\s*(연도|년도)\s*[:：]\s*(\d{4})/
    ],
    organization: [
      /발급\s*기관\s*[:：]\s*([^\n\r]+)/,
      /교육\s*기관\s*[:：]\s*([^\n\r]+)/,
      /주관\s*[:：]\s*([^\n\r]+)/
    ],
    serial: [
      /문서\s*번호\s*[:：]\s*([A-Z0-9-]+)/i,
      /인증서\s*번호\s*[:：]\s*([A-Z0-9-]+)/i,
      /발급\s*번호\s*[:：]\s*([A-Z0-9-]+)/i
    ]
  };

  const extract = (field, patterns) => {
    for (const pattern of patterns) {
      const match = text.match(pattern);
      if (match) {
        return field === 'year' ? match[2] : match[1].trim();
      }
    }
    return null;
  };

  const name = extract('name', patterns.name);
  const year = extract('year', patterns.year);
  const organization = extract('organization', patterns.organization);
  const serial = extract('serial', patterns.serial);

  if (name && year && organization && serial) {
    return {
      success: true,
      data: { name, year, organization, serial }
    };
  }
  return { success: false };
}

/**
 * AI 기반 파싱 (GPT-4o mini)
 */
async function parseByAI(text) {
  const systemPrompt = `너는 교육 인증서에서 정보를 추출하는 전문 AI야.
주어진 텍스트에서 아래 JSON 형식으로 정보를 추출해줘.
찾을 수 없는 필드는 null로 표기해.

{
  "name": "수강자 성명",
  "year": "이수 연도 (YYYY)",
  "organization": "발급 기관명",
  "serial": "인증서 고유 번호"
}`;

  const messages = [
    { role: 'system', content: systemPrompt },
    { role: 'user', content: text }
  ];

  const response = await client.getChatCompletions(deploymentName, messages, {
    responseFormat: { type: 'json_object' },
    maxTokens: 300,
    temperature: 0.1
  });

  const content = response.choices[0].message.content;
  const parsed = JSON.parse(content);

  const success = !!(parsed.name && parsed.year && parsed.organization && parsed.serial);
  return {
    success,
    data: parsed,
    confidence: success ? 0.9 : 0.5,
    failedFields: success ? [] : ['name', 'year', 'organization', 'serial'].filter(f => !parsed[f])
  };
}

/**
 * 메인 AI 파싱 함수 (Rate Limit 포함)
 */
async function callAIWithRateLimit(pdfBuffer, fileHash) {
  const allowed = await checkAIRateLimit(fileHash);
  if (!allowed) {
    return { success: false, failedFields: ['rate_limited'] };
  }

  let text = '';
  try {
    const data = await pdfParse(pdfBuffer);
    text = data.text;
    if (!text || text.trim().length === 0) {
      return { success: false, failedFields: ['pdf_no_text'] };
    }
  } catch (err) {
    console.error('PDF parsing error:', err);
    return { success: false, failedFields: ['pdf_parse_error'] };
  }

  const ruleResult = parseByRule(text);
  if (ruleResult.success) {
    return {
      success: true,
      source: 'rule',
      data: ruleResult.data,
      confidence: 1.0
    };
  }

  try {
    const aiResult = await parseByAI(text);
    return {
      success: aiResult.success,
      source: 'gpt-4o-mini',
      data: aiResult.data,
      confidence: aiResult.confidence,
      failedFields: aiResult.failedFields
    };
  } catch (err) {
    console.error('AI parsing error:', err);
    return { success: false, failedFields: ['ai_error'] };
  }
}

module.exports = { callAIWithRateLimit };
