; Vértice PDF — Inno Setup 6.3+.  Compile com:  python build.py
; Instalação silenciosa (TI):  VerticePDF-Setup-x.y.z.exe /VERYSILENT /ALLUSERS /TASKS="assoc"
#ifndef AppVersion
  #define AppVersion "1.4.2"
#endif
#define AppName "Vértice PDF"
#define AppDir  "VerticePDF"
#define AppExe  "VerticePDF.exe"

[Setup]
AppId={{B7C1E0D2-4F3A-4E5B-9A6C-1D2E3F4A5B6C}
AppName={#AppName}
AppVersion={#AppVersion}
AppVerName={#AppName} {#AppVersion}
AppPublisher={#AppName}
VersionInfoVersion={#AppVersion}
DefaultDirName={autopf}\{#AppDir}
DisableProgramGroupPage=yes
OutputDir=installer
OutputBaseFilename=VerticePDF-Setup-{#AppVersion}
SetupIconFile=assets\verticepdf.ico
UninstallDisplayIcon={app}\{#AppExe}
Compression=lzma2/ultra64
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
MinVersion=10.0
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog commandline
CloseApplications=yes
RestartApplications=no
ChangesAssociations=yes
SetupLogging=yes
InfoBeforeFile=THIRD_PARTY_NOTICES.txt

[Languages]
Name: "brazilianportuguese"; MessagesFile: "compiler:Languages\BrazilianPortuguese.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Types]
Name: "full"; Description: "Instalação completa (recomendado)"
Name: "compact"; Description: "Compacta (sem OCR)"
Name: "custom"; Description: "Personalizada"; Flags: iscustom

[Components]
Name: "main"; Description: "Vértice PDF"; Types: full compact custom; Flags: fixed
#ifdef WITH_OCR
Name: "ocr"; Description: "OCR — reconhecimento de texto (Tesseract, português e inglês)"; Types: full
#endif

[Tasks]
Name: "desktopicon"; Description: "Criar atalho na área de trabalho"; GroupDescription: "Atalhos:"; Flags: unchecked
Name: "assoc"; Description: "Abrir arquivos .pdf com o {#AppName}"; GroupDescription: "Associações:"; Flags: unchecked

[Files]
Source: "dist\VerticePDF\*"; DestDir: "{app}"; Flags: recursesubdirs createallsubdirs ignoreversion; Components: main
Source: "THIRD_PARTY_NOTICES.txt"; DestDir: "{app}"; Flags: ignoreversion; Components: main
#ifdef WITH_OCR
Source: "redist\tesseract\*"; DestDir: "{app}\tesseract"; Flags: recursesubdirs createallsubdirs ignoreversion; Components: ocr
#endif
#ifdef WITH_VCREDIST
Source: "redist\vc_redist.x64.exe"; DestDir: "{tmp}"; Flags: ignoreversion; Check: NeedsVCRedist
#endif

[Icons]
Name: "{autoprograms}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
Root: HKA; Subkey: "Software\Classes\VerticePDF.pdf"; ValueType: string; ValueData: "Documento PDF"; Flags: uninsdeletekey; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\VerticePDF.pdf\DefaultIcon"; ValueType: string; ValueData: "{app}\{#AppExe},0"; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\VerticePDF.pdf\shell\open\command"; ValueType: string; ValueData: """{app}\{#AppExe}"" ""%1"""; Tasks: assoc
Root: HKA; Subkey: "Software\Classes\.pdf\OpenWithProgids"; ValueType: string; ValueName: "VerticePDF.pdf"; ValueData: ""; Flags: uninsdeletevalue; Tasks: assoc

[Run]
Filename: "{app}\{#AppExe}"; Description: "Abrir o {#AppName}"; Flags: nowait postinstall skipifsilent
; Atualização iniciada de dentro do programa (/UPDATED=1): reabre o app sozinho ao terminar.
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: IsInAppUpdate

[Code]
function IsInAppUpdate: Boolean;
begin
  Result := ExpandConstant('{param:UPDATED|0}') = '1';
end;

// Qt/PyMuPDF precisam do Microsoft Visual C++ Runtime 2015-2022; PCs limpos podem não ter.
function NeedsVCRedist: Boolean;
var
  Installed, Bld: Cardinal;
begin
  Result := True;
  if RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Installed', Installed) and
     RegQueryDWordValue(HKLM64, 'SOFTWARE\Microsoft\VisualStudio\14.0\VC\Runtimes\x64', 'Bld', Bld) then
    Result := (Installed <> 1) or (Bld < 30000);
end;

procedure CurStepChanged(CurStep: TSetupStep);
var
  ResultCode: Integer;
  Redist: String;
begin
  if CurStep = ssPostInstall then
  begin
    Redist := ExpandConstant('{tmp}\vc_redist.x64.exe');
    if FileExists(Redist) then
    begin
      WizardForm.StatusLabel.Caption := 'Instalando o Microsoft Visual C++ Runtime...';
      if not Exec(Redist, '/install /quiet /norestart', '', SW_HIDE, ewWaitUntilTerminated, ResultCode) then
        Log('Falha ao executar o VC++ Redistributable')
      else
        Log('VC++ Redistributable terminou com codigo ' + IntToStr(ResultCode));
    end;
  end;
end;
