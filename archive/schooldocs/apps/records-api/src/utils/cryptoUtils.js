const crypto = require('crypto');
const { getSecret } = require('./keyvault');

let aesKey = null;
let hmacKey = null;
let keysPromise = null;

async function loadKeys() {
  if (!keysPromise) {
    keysPromise = (async () => {
      const aesHex = await getSecret('encryption-key-aes');
      const hmacHex = await getSecret('encryption-key-hmac');
      aesKey = Buffer.from(aesHex, 'hex');
      hmacKey = Buffer.from(hmacHex, 'hex');
    })();
  }
  await keysPromise;
}

async function ensureKeysLoaded() {
  if (!aesKey || !hmacKey) {
    await loadKeys();
  }
}

async function encrypt(text) {
  await ensureKeysLoaded();
  const iv = crypto.randomBytes(16);
  const cipher = crypto.createCipheriv('aes-256-cbc', aesKey, iv);
  let encrypted = cipher.update(text, 'utf8', 'hex');
  encrypted += cipher.final('hex');
  return iv.toString('hex') + ':' + encrypted;
}

async function decrypt(encryptedText) {
  await ensureKeysLoaded();
  const parts = encryptedText.split(':');
  if (parts.length !== 2) throw new Error('Invalid encrypted format');
  const iv = Buffer.from(parts[0], 'hex');
  const encrypted = parts[1];
  const decipher = crypto.createDecipheriv('aes-256-cbc', aesKey, iv);
  let decrypted = decipher.update(encrypted, 'hex', 'utf8');
  decrypted += decipher.final('utf8');
  return decrypted;
}

async function hashPersonId(name, birthdate) {
  await ensureKeysLoaded();
  const normalizedName = name.normalize('NFC').trim().replace(/\s+/g, ' ');
  if (!/^\d{4}-(0[1-9]|1[0-2])-(0[1-9]|[12]\d|3[01])$/.test(birthdate)) {
    throw new Error('Invalid birthdate format');
  }
  const message = `personId|${normalizedName}|${birthdate}`;
  return crypto.createHmac('sha256', hmacKey).update(message).digest('hex');
}

module.exports = { encrypt, decrypt, hashPersonId };
