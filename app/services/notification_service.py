import aiohttp
from app.core.config import settings
import logging

logger = logging.getLogger(__name__)

class NotificationService:
    @staticmethod
    async def _call_apps_script(action: str, payload: dict):
        """Helper to call Google Apps Script backend."""
        if not settings.SHEET_URL:
            logger.warning("SHEET_URL not configured. Skipping Apps Script call.")
            return False

        try:
            async with aiohttp.ClientSession() as session:
                data = {
                    "action": action,
                    "payload": payload
                }
                async with session.post(settings.SHEET_URL, json=data) as response:
                    if response.status == 200:
                        resp_json = await response.json()
                        if resp_json.get("success"):
                            logger.info(f"Apps Script action '{action}' successful.")
                            return True
                        else:
                            logger.error(f"Apps Script action '{action}' failed: {resp_json.get('message')}")
                            return False
                    else:
                        text = await response.text()
                        logger.error(f"Apps Script HTTP error: {text}")
                        return False
        except Exception as e:
            logger.error(f"Failed to communicate with Apps Script: {e}")
            return False

    @staticmethod
    async def send_email(to_email: str, subject: str, body: str, is_html: bool = True):
        """Sends an email using Google Apps Script MailApp."""
        payload = {
            "to": to_email,
            "subject": subject,
            "htmlBody": body if is_html else None,
            "body": body if not is_html else None
        }
        return await NotificationService._call_apps_script("sendEmail", payload)

    @staticmethod
    async def send_telegram(message: str):
        """Sends a message via Google Apps Script Telegram handler."""
        payload = {
            "message": message
        }
        return await NotificationService._call_apps_script("sendTelegram", payload)

    @staticmethod
    def get_subscription_email_template(details: dict):
        """Returns a professional HTML email template for subscriptions."""
        return f"""
        <!DOCTYPE html>
        <html>
        <head>
            <style>
                body {{ font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; line-height: 1.6; color: #333; }}
                .container {{ width: 80%; margin: 20px auto; border: 1px solid #ddd; border-radius: 8px; overflow: hidden; box-shadow: 0 4px 15px rgba(0,0,0,0.1); }}
                .header {{ background: linear-gradient(135deg, #1e3c72 0%, #2a5298 100%); color: white; padding: 30px; text-align: center; }}
                .content {{ padding: 30px; background: #fff; }}
                .footer {{ background: #f9f9f9; padding: 20px; text-align: center; font-size: 12px; color: #777; border-top: 1px solid #eee; }}
                .details-table {{ width: 100%; border-collapse: collapse; margin: 20px 0; }}
                .details-table th, .details-table td {{ padding: 12px; border-bottom: 1px solid #eee; text-align: left; }}
                .details-table th {{ color: #1e3c72; font-weight: 600; width: 40%; }}
                .badge {{ background: #e3f2fd; color: #1976d2; padding: 4px 12px; border-radius: 20px; font-size: 12px; font-weight: bold; }}
                .button {{ display: inline-block; padding: 12px 25px; background: #1e3c72; color: white; text-decoration: none; border-radius: 5px; margin-top: 20px; }}
                .receipt-card {{ background: #f8f9fa; border-radius: 10px; padding: 20px; margin-top: 20px; border-left: 4px solid #1e3c72; }}
            </style>
        </head>
        <body>
            <div class="container">
                <div class="header">
                    <h1 style="margin:0;">Subscription Confirmation</h1>
                    <p style="margin:10px 0 0 0; opacity:0.9;">CHN IT Asset Management System</p>
                </div>
                <div class="content">
                    <p>Dear <strong>{details.get('user_name', 'Valued Customer')}</strong>,</p>
                    <p>Your subscription for <strong>{details.get('plan_name', 'Standard Plan')}</strong> has been successfully processed.</p>
                    
                    <h3>Subscription Details</h3>
                    <table class="details-table">
                        <tr>
                            <th>Subscription ID</th>
                            <td><code>{details.get('subscription_id', 'SUB-12345')}</code></td>
                        </tr>
                        <tr>
                            <th>Plan</th>
                            <td><span class="badge">{details.get('plan_name', 'Standard Plan')}</span></td>
                        </tr>
                        <tr>
                            <th>Amount Paid</th>
                            <td><strong>{details.get('amount', '$0.00')}</strong></td>
                        </tr>
                        <tr>
                            <th>Renewal Date</th>
                            <td>{details.get('renewal_date', 'N/A')}</td>
                        </tr>
                        <tr>
                            <th>Status</th>
                            <td>Active</td>
                        </tr>
                    </table>

                    <div class="receipt-card">
                        <h4 style="margin-top:0; color:#1e3c72;">Payment Receipt</h4>
                        <p style="margin-bottom:5px;">Transaction Reference: <strong>{details.get('transaction_id', 'TXN-98765')}</strong></p>
                        <p style="margin-bottom:5px;">Date: <strong>{details.get('date', '2024-04-30')}</strong></p>
                        <p style="margin-top:15px; font-size:14px; color:#666;">This is an automated receipt for your records.</p>
                    </div>

                    <a href="#" class="button">Manage Subscription</a>
                </div>
                <div class="footer">
                    <p>&copy; 2024 CHN IT Solutions. All rights reserved.</p>
                    <p>You received this email because you are a registered user of ITAMS.</p>
                </div>
            </div>
        </body>
        </html>
        """

    @staticmethod
    def get_subscription_telegram_template(details: dict):
        """Returns a formatted Telegram message."""
        return f"""
<b>🔔 New Subscription Alert</b>

<b>User:</b> {details.get('user_name', 'Valued Customer')}
<b>Plan:</b> {details.get('plan_name', 'Standard Plan')}
<b>Amount:</b> {details.get('amount', '$0.00')}
<b>ID:</b> <code>{details.get('subscription_id', 'SUB-12345')}</code>

✅ Subscription is now <b>Active</b>.
        """
