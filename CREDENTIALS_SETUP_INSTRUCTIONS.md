# OAuth Credentials Setup for Alpha Testers

## 📧 You Should Have Received

Along with the EmiAi application files, you should have received a file named:
- `credentials.json`

This file contains the OAuth client credentials needed for Google services (Gmail, Calendar, Tasks).

## 📁 Installation Steps

### 1. Locate the credentials directory

After extracting the EmiAi application, navigate to:
```
EmiAi_alpha/app/assistant/lib/credentials/
```

### 2. Place the credentials file

Copy the `credentials.json` file you received via email into this directory.

**Final path should be:**
```
EmiAi_alpha/app/assistant/lib/credentials/credentials.json
```

### 3. Verify

The `credentials/` directory should now contain:
- `credentials.json` ✅ (the file you just placed)

**Do NOT place any other files here.** The application will create additional files (`token.pickle`) when you authenticate with Google.

## 🔒 Security Notes

- **Keep `credentials.json` private** - don't share it publicly
- **Never commit it to Git** if you're modifying the code
- This file identifies the EmiAi application to Google
- Your personal Google data is only accessible after you authenticate through the setup wizard

## ❓ Troubleshooting

**"credentials.json not found" error:**
- Verify the file is in the correct location
- Check the filename is exactly `credentials.json` (not `credentials.json.txt`)
- Ensure the file is not empty

**OAuth errors during setup:**
- Make sure you're using the file sent by the developer
- Don't edit or modify the contents of `credentials.json`
- Contact the developer if issues persist

## 📞 Need Help?

If you encounter any issues with the credentials setup, please contact the developer who sent you the alpha package.

