; -*- coding: utf-8 -*-
; A 股 ETF 工具台 Inno Setup 安装脚本
; 编译: ISCC.exe installer.iss
; 输出: installer-output/ETF-Tools-Setup-v1.3.exe
#define MyAppName "A 股 ETF 工具台"
#define MyAppShortName "ETF 工具台"
#define MyAppVersion "1.3"
#define MyAppPublisher "weiyuan0917-a11y"
#define MyAppURL "https://github.com/weiyuan0917-a11y/etf-dashboard"
#define MyAppExeName "start.bat"

[Setup]
; 安装程序自身的标识(每次构建必须固定,Windows 用它跟踪安装/卸载)
AppId={{D0E5C123-4567-89AB-CDEF-1234567890AB}
AppName={#MyAppName}
AppVersion={#MyAppVersion}
AppVerName={#MyAppName} v{#MyAppVersion}
AppPublisher={#MyAppPublisher}
AppPublisherURL={#MyAppURL}
AppSupportURL={#MyAppURL}/issues
AppUpdatesURL={#MyAppURL}/releases
; 默认安装到用户 AppData(可写,streamlit 要写 data/etf.db)
DefaultDirName={userappdata}\{#MyAppShortName}
; 不允许用户改 Programs Files(避免权限问题)
PrivilegesRequired=lowest
PrivilegesRequiredOverridesAllowed=dialog
; 输出目录
OutputDir=installer-output
OutputBaseFilename=ETF-Tools-Setup-v{#MyAppVersion}
; 使用快速 LZMA2，优先保证包含便携运行时的安装包能稳定完成构建。
Compression=lzma2/fast
; 最小 Windows 版本: Win 10 1809 (10.0.17763) - Python 3.13 要求
MinVersion=10.0.17763
; 64 位 only(项目只支持 64)
ArchitecturesAllowed=x64compatible
ArchitecturesInstallIn64BitMode=x64compatible
; 美化
WizardStyle=modern
WizardSizePercent=120
DisableWelcomePage=no
; 卸载: 显示"删除所有数据" 选项
UninstallDisplayIcon={app}\{#MyAppExeName}
UninstallDisplayName={#MyAppShortName}

[Languages]
Name: "chinesesimp"; MessagesFile: "compiler:Languages\ChineseSimplified.isl"
Name: "english"; MessagesFile: "compiler:Default.isl"

[Tasks]
Name: "startmenuicon"; Description: "在开始菜单创建快捷方式"; GroupDescription: "附加快捷方式:"; Flags: checkedonce

[Files]
; 1. 项目源代码(除 build/ / data/ / __pycache__/ / .git/)
Source: "app.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "config.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "charts.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "ui_theme.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "storage.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "live.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "llm.py"; DestDir: "{app}"; Flags: ignoreversion
Source: "requirements.txt"; DestDir: "{app}"; Flags: ignoreversion
Source: "README.md"; DestDir: "{app}"; Flags: ignoreversion
Source: "LICENSE"; DestDir: "{app}"; Flags: ignoreversion
Source: "start.bat"; DestDir: "{app}"; Flags: ignoreversion
Source: "pages\*"; DestDir: "{app}\pages"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "metrics\*"; DestDir: "{app}\metrics"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "collector\*"; DestDir: "{app}\collector"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "scripts\*"; DestDir: "{app}\scripts"; Flags: ignoreversion recursesubdirs createallsubdirs
Source: "docs\*"; DestDir: "{app}\docs"; Flags: ignoreversion recursesubdirs createallsubdirs
; 2. 完整便携式 Python + 依赖
; 不使用 venv: venv 的 pyvenv.cfg 会写死开发机 Python 路径,换电脑后无法启动
Source: "build\runtime\*"; DestDir: "{app}\runtime"; Flags: ignoreversion recursesubdirs createallsubdirs
; 注意: 安装包 {app} = {userappdata}\ETF-Tools, 用户可写(数据 db 写入 {app}\data)

[Icons]
; 开始菜单组 "ETF 工具台"
Name: "{group}\启动 {#MyAppShortName}"; Filename: "{app}\{#MyAppExeName}"; Tasks: startmenuicon
Name: "{group}\打开安装目录"; Filename: "{app}"; Tasks: startmenuicon
Name: "{group}\项目主页 (GitHub)"; Filename: "{#MyAppURL}"; Tasks: startmenuicon
Name: "{group}\{cm:UninstallProgram,{#MyAppShortName}}"; Filename: "{uninstallexe}"; Tasks: startmenuicon

[Run]
; 安装完提示"立即启动"
Filename: "{app}\{#MyAppExeName}"; Description: "{cm:LaunchProgram,{#MyAppShortName}}"; Flags: nowait postinstall skipifsilent

[UninstallDelete]
; 卸载时清空 data 目录(用户持仓/网格/AI 复盘)
Type: filesandordirs; Name: "{app}\data"
; 清空日志
Type: filesandordirs; Name: "{app}\logs"

[Messages]
; 简体中文微调
BeveledLabel=ETF 工具台 v{#MyAppVersion}
SetupWindowTitle=安装 {#MyAppName}

[Code]
// 阻止安装到含空格的 Programs Files(避免某些 pip wheel 出错)
function IsNotInProgramFilesDir(Dir: string): Boolean;
begin
  Result := not((Pos('Program Files', Dir) > 0) or (Pos('Program Files (x86)', Dir) > 0));
end;

function InitializeSetup(): Boolean;
begin
  // 允许装到 {userappdata}\ETF-Tools(默认)
  // 如果用户改路径到 Programs Files,虽然 PrivilegesRequired=lowest,有些机器还是需要管理员
  // 不强制拦截,只给个提示
  Result := True;
end;
