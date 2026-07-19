# Publishing NaiTRO To GitHub

Use these steps when you are ready to put NaiTRO online.

## 1. Create A GitHub Repo

Create a new empty repository on GitHub, for example:

```text
naitro-pc-assistant
```

Do not add a README, license, or `.gitignore` on GitHub. This project already has them.

## 2. Push The Code

Run these commands from the project folder:

```powershell
git init
git add .
git status
git commit -m "Initial NaiTRO release"
git branch -M main
git remote add origin https://github.com/YOUR_USERNAME/naitro-pc-assistant.git
git push -u origin main
```

Check `git status` before committing. `config.json`, `build/`, and `dist/` should not be staged.

If `config.json` ever shows up as tracked, remove it from git without deleting your local copy:

```powershell
git rm --cached config.json
git commit -m "Keep local config private"
```

## 3. Build A Downloadable EXE

After pushing, open the repo on GitHub:

1. Go to **Actions**.
2. Choose **Build Windows EXE**.
3. Click **Run workflow**.
4. Download the `NaiTRO-Windows` artifact when it finishes.

## 4. Create A Public Release

To publish a proper release page with `NaiTRO.exe`, push a version tag:

```powershell
git tag v1.0.0
git push origin v1.0.0
```

The GitHub workflow will build the exe and attach it to a new release.

## Notes For Friends

- Windows SmartScreen may warn them because the app is not code-signed.
- They should keep `NaiTRO.exe` in its own folder.
- On first launch, NaiTRO creates their own `config.json`.
- They can add their own apps, websites, folders, and modes from the UI.
