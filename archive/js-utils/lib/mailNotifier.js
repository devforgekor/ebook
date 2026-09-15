// lib/mailNotifier | SMTP failure-notification mailer with env-based config guard.
// Never throws: logs and returns false on any misconfiguration/send error so it is
// safe to call from a catch block without masking the original failure.
// source: kuhwa scripts/fetch-schedule.js (sendFailureMail)

const nodemailer = require("nodemailer");

/**
 * Send a plain-text failure notification email using SMTP_* environment
 * variables (or an explicit config object).
 *
 * @param {{
 *   subject: string,
 *   text: string,
 *   config?: {
 *     host?: string, port?: number, user?: string, password?: string, to?: string,
 *   },
 * }} params
 * @returns {Promise<boolean>} true if the mail was sent, false otherwise.
 */
async function sendFailureMail({ subject, text, config = {} }) {
  const host = config.host ?? process.env.SMTP_HOST;
  const port = config.port ?? Number(process.env.SMTP_PORT || 587);
  const user = config.user ?? process.env.SMTP_USER;
  const password = config.password ?? process.env.SMTP_PASSWORD;
  const to = config.to ?? process.env.MAIL_TO ?? user;

  if (!host || !user || !password) {
    console.error("[mailNotifier] SMTP 환경변수가 설정되어 있지 않아 알림 메일을 보낼 수 없습니다.");
    return false;
  }

  try {
    const transporter = nodemailer.createTransport({
      host,
      port,
      secure: false,
      auth: { user, pass: password },
    });
    await transporter.sendMail({ from: user, to, subject, text });
    console.log("[mailNotifier] 알림 메일을 발송했습니다.");
    return true;
  } catch (mailErr) {
    console.error("[mailNotifier] 알림 메일 발송 중 오류:", mailErr);
    return false;
  }
}

module.exports = { sendFailureMail };
