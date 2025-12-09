# Installing Java for Firebase Emulators

Firebase emulators require Java to run locally. Here are installation options:

## Option 1: Install Java JDK (Recommended)

1. Download Java JDK 17 or later from:
   - https://adoptium.net/ (OpenJDK - recommended)
   - Or https://www.oracle.com/java/technologies/downloads/

2. Install Java and add it to your PATH

3. Verify installation:
   ```powershell
   java -version
   ```

## Option 2: Use Chocolatey (Windows Package Manager)

If you have Chocolatey installed:
```powershell
choco install openjdk17
```

## Option 3: Skip Emulators (Recommended for now)

You can deploy directly to Firebase without using emulators. The Blaze plan has a generous free tier, and you only pay for what you use beyond the free limits.

## After Installing Java

Once Java is installed, you can run:
```powershell
firebase emulators:start
```

This will start:
- Firestore Emulator
- Functions Emulator
- Hosting Emulator (for testing React app locally)

