const dotenv = require("dotenv");
const cors = require("cors");
const express = require("express");
const { sendTestEmail, transporter } = require("./mailer");

dotenv.config();

const app = express();
const port = Number(process.env.EMAIL_SERVICE_PORT || 5001);

app.use(cors());
app.use(express.json());

app.get("/health", (_req, res) => {
  res.json({ status: "ok", message: "Fair Drop email service is running" });
});

app.post("/send-test-email", async (req, res) => {
  const { to } = req.body || {};

  if (!to || typeof to !== "string") {
    return res
      .status(400)
      .json({ error: "The 'to' recipient email is required." });
  }

  try {
    const info = await sendTestEmail(to);
    return res.json({
      success: true,
      message: "Test email sent.",
      messageId: info.messageId,
    });
  } catch (error) {
    console.error("Email delivery failed:", error.message);
    return res.status(502).json({
      success: false,
      error: "Email delivery failed. Check the SMTP configuration.",
    });
  }
});

app.listen(port, () => {
  console.log(`Fair Drop email service listening on port ${port}`);
  transporter.verify((error) => {
    if (error) {
      console.error("SMTP verification failed:", error.code || error.message);
      return;
    }
    console.log("SMTP connection verified successfully");
  });
});
