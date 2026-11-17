; ============================================================================
;  Compresorfree -- Instalador (Inno Setup 6+)
;
;  Lo compila el workflow .github/workflows/compilar.yml en Windows, desde
;  dist\Compresorfree (resultado de compilar.py):
;      iscc /DMyAppVersion=1.2.0 /FCompresorfree-Setup-1.2.0 installer\compresorfree.iss
;  Salida: installer\Output\Compresorfree-Setup-X.Y.Z.exe
;
;  Contrato con la app (actualizador.py / instalador_constantes.py):
;    /SILENT /SUPPRESSMSGBOXES /NORESTART /CLOSEAPPLICATIONS /CURRENTUSER
;    /REABRIR=1   -> al terminar, relanza Compresorfree.exe
;    /SINAL=<ruta> -> al arrancar, crea ese archivo: la app sabe que ya puede cerrarse
;  tests/test_instalador_iss.py comprueba este archivo por contenido. Que pase no
;  prueba que COMPILE: eso solo lo dice Inno Setup en Windows.
; ============================================================================

#ifndef MyAppVersion
  #define MyAppVersion "1.0.0"
#endif

; VersionInfoVersion solo admite digitos: una pre-release (1.3.0-rc.1) necesita una
; version numerica aparte. Se calcula aqui si no se pasa /DMyVersionInfo.
#ifndef MyVersionInfo
  #if Pos("-", MyAppVersion) > 0
    #define MyVersionInfo Copy(MyAppVersion, 1, Pos("-", MyAppVersion) - 1)
  #else
    #define MyVersionInfo MyAppVersion
  #endif
#endif

#define AppName "Compresorfree"
#define AppExe "Compresorfree.exe"

[Setup]
AppId={{6D1B7E52-3C9A-4F80-B2A4-8E5F0C7D9A13}
AppName={#AppName}
AppVersion={#MyAppVersion}
AppVerName={#AppName} {#MyAppVersion}
VersionInfoVersion={#MyVersionInfo}
AppPublisher=Compresorfree
AppUpdatesURL=https://github.com/Jonann17/Compresorfree/releases
DefaultDirName={localappdata}\Programs\Compresorfree
DefaultGroupName={#AppName}
DisableProgramGroupPage=yes
OutputDir=Output
OutputBaseFilename=Compresorfree-Setup-{#MyAppVersion}
Compression=lzma2
SolidCompression=yes
WizardStyle=modern
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
UninstallDisplayIcon={app}\{#AppExe}

; Instalacion siempre por usuario (sin pedir administrador); la linea de comandos
; puede subir el nivel (/ALLUSERS) si hiciera falta.
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=commandline

; Cierra la app si sigue abierta antes de copiar los archivos.
CloseApplications=force
RestartApplications=no

[Languages]
Name: "spanish"; MessagesFile: "compiler:Languages\Spanish.isl"

[Tasks]
Name: "desktopicon"; Description: "Crear un acceso directo en el Escritorio"; GroupDescription: "Accesos directos:"; Flags: unchecked

[InstallDelete]
; Una actualizacion no debe mezclar bibliotecas viejas con las nuevas.
Type: filesandordirs; Name: "{app}\_internal"

[Files]
Source: "..\dist\Compresorfree\*"; DestDir: "{app}"; Flags: recursesubdirs ignoreversion

[Icons]
Name: "{group}\{#AppName}"; Filename: "{app}\{#AppExe}"
Name: "{group}\Desinstalar {#AppName}"; Filename: "{uninstallexe}"
Name: "{autodesktop}\{#AppName}"; Filename: "{app}\{#AppExe}"; Tasks: desktopicon

[Registry]
; La app lee estas claves para saber que se instalo con este instalador (y por tanto
; puede autoactualizarse). Se borran al desinstalar.
Root: HKCU; Subkey: "Software\Compresorfree"; ValueType: string; ValueName: "InstallPath"; ValueData: "{app}"; Flags: uninsdeletekey
Root: HKCU; Subkey: "Software\Compresorfree"; ValueType: string; ValueName: "Version"; ValueData: "{#MyAppVersion}"

[Run]
; Instalacion a mano: casilla "Abrir Compresorfree" al final del asistente.
Filename: "{app}\{#AppExe}"; Description: "Abrir {#AppName}"; Flags: nowait postinstall skipifsilent
; Actualizacion automatica (/REABRIR=1): relanza la app con el usuario original.
Filename: "{app}\{#AppExe}"; Flags: nowait runasoriginaluser; Check: Reabrir

[UninstallDelete]
Type: dirifempty; Name: "{app}"

[Code]
// Verdadero solo si la actualizacion automatica de la app paso /REABRIR=1
// (instalador_constantes.FLAGS_INSTALADOR). Si el nombre no coincide no hay error: la
// app simplemente no se reabre.
function Reabrir: Boolean;
begin
  Result := ExpandConstant('{param:REABRIR|0}') = '1';
end;

// El instalador avisa de que ARRANCO: la app pasa /SINAL=<archivo> y solo se cierra
// cuando ese archivo existe. Si el instalador muere antes (antivirus, UAC rechazado), la
// app sigue abierta y lo explica. Sin /SINAL no pasa nada.
function InitializeSetup(): Boolean;
var
  Sinal: String;
begin
  Sinal := ExpandConstant('{param:SINAL|}');
  if Sinal <> '' then
    SaveStringToFile(Sinal, 'listo', False);
  Result := True;
end;
