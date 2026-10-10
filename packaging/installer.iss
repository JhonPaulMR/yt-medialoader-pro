; Inno Setup 6 — gera dist\MediaLoader-Setup.exe a partir de dist\MediaLoader (PyInstaller).
; Compilar: ISCC packaging\installer.iss   (o build.ps1 faz isso)

#define AppName "MediaLoader Pro"
#define AppVersion "2.1.0"
#define AppExe "MediaLoader.exe"

[Setup]
AppId={{8F3C2A51-6E0B-4C7D-9A51-3B7E2D9C4F10}
AppName={#AppName}
AppVersion={#AppVersion}
AppPublisher=MediaLoader
; Instalação por usuário: não pede administrador e a pasta é gravável.
PrivilegesRequired=lowest
DefaultDirName={localappdata}\Programs\MediaLoader
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=..\dist
OutputBaseFilename=MediaLoader-Setup
SetupIconFile=..\assets\icon.ico
UninstallDisplayIcon={app}\{#AppExe}
UninstallDisplayName={#AppName}
Compression=lzma2/max
SolidCompression=yes
WizardStyle=modern
InfoAfterFile=pos-instalacao.txt

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na Área de Trabalho"; GroupDescription: "Atalhos:"

[Files]
Source: "..\dist\MediaLoader\*"; DestDir: "{app}"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "..\README.md"; DestDir: "{app}"; DestName: "Manual.md"; Flags: ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Manual do MediaLoader"; Filename: "{win}\notepad.exe"; Parameters: """{app}\Manual.md"""
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppName}"; Flags: nowait postinstall skipifsilent

; Os dados do usuário (%LOCALAPPDATA%\MediaLoader: configurações, cookies,
; playlists, logs) e as músicas NÃO são apagados na desinstalação.
