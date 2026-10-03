const dotenv = require("dotenv");
const nodemailer = require("nodemailer");

dotenv.config();

const smtpPort = Number(process.env.SMTP_PORT || 587);

const transporter = nodemailer.createTransport({
  host: process.env.SMTP_HOST,
  port: smtpPort,
  secure: smtpPort === 465,
  auth: {
    user: process.env.SMTP_USER,
    pass: process.env.SMTP_PASSWORD,
  },
});

async function sendTestEmail(to) {
  return transporter.sendMail({
    from: process.env.EMAIL_FROM || process.env.SMTP_USER,
    to,
    subject: "Fair Drop email service test",
    text: "This is a test email from the Fair Drop email service.",
  });
}

module.exports = { sendTestEmail, transporter };
