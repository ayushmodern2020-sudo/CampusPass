CAMPUSPASS ACTUAL EMAIL UPDATE

This update preserves your existing app.py, templates, static files, database, and .env.

1. Extract this email_update folder into your existing WEB04_Event_Ticketing_System folder.
2. Open PowerShell in WEB04_Event_Ticketing_System.
3. Run:

   powershell -ExecutionPolicy Bypass -File .\email_update\apply_email_update.ps1

4. Then run:

   python setup_email.py

5. Test delivery:

   python send_test_email.py your-email@example.com

6. Restart Flask:

   python app.py

After MAIL_MODE=resend is configured, normal ticket booking automatically sends the ticket email.

Keep .env private. Never commit RESEND_API_KEY to GitHub.
