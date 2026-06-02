const { app, BrowserWindow, ipcMain } = require("electron");
const { spawn } = require("child_process");
const path = require("path");

let mainWindow;
let pythonProcess;

function startPython() {
  const projectRoot = path.join(__dirname, "..");
  pythonProcess = spawn("python", ["-m", "backend.main"], {
    cwd: projectRoot,
    env: { ...process.env, PYTHONPATH: projectRoot },
  });

  pythonProcess.stdout.on("data", (data) => {
    console.log(`[backend] ${data}`);
  });

  pythonProcess.stderr.on("data", (data) => {
    console.error(`[backend] ${data}`);
  });

  pythonProcess.on("close", (code) => {
    console.log(`[backend] exited with code ${code}`);
  });
}

function createWindow() {
  mainWindow = new BrowserWindow({
    width: 1100,
    height: 720,
    minWidth: 800,
    minHeight: 560,
    titleBarStyle: "hiddenInset",
    backgroundColor: "#0f1117",
    webPreferences: {
      nodeIntegration: true,
      contextIsolation: false,
    },
  });

  const htmlPath = path.join(__dirname, "app.html");
  console.log("[main] loading", htmlPath);
  mainWindow.loadFile(htmlPath);
  mainWindow.webContents.on("did-fail-load", (e, code, desc) => {
    console.error("[main] load failed:", code, desc);
  });
  mainWindow.webContents.on("did-finish-load", () => {
    console.log("[main] window loaded OK");
  });
  mainWindow.on("closed", () => { mainWindow = null; });
}

app.whenReady().then(() => {
  startPython();
  // Give the Python server 2 seconds to start before opening the window
  setTimeout(createWindow, 2000);
});

app.on("window-all-closed", () => {
  if (pythonProcess) pythonProcess.kill();
  if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
  if (mainWindow === null) createWindow();
});
