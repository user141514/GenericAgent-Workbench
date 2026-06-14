const { app, BrowserWindow, Menu, shell } = require("electron");
const path = require("node:path");
const {
  createTextEditingMenuTemplate,
  shouldShowTextEditingMenu,
} = require("./text-context-menu.cjs");

const DEV_URL = process.env.GA_REACT_DESKTOP_URL || "http://127.0.0.1:5173";

function createWindow() {
  const win = new BrowserWindow({
    title: "GenericAgent",
    width: 1180,
    height: 820,
    minWidth: 860,
    minHeight: 620,
    backgroundColor: "#fffdfa",
    show: false,
    webPreferences: {
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });

  win.once("ready-to-show", () => win.show());
  win.webContents.setWindowOpenHandler(({ url }) => {
    shell.openExternal(url);
    return { action: "deny" };
  });
  win.webContents.on("context-menu", (_event, params) => {
    if (!shouldShowTextEditingMenu(params)) return;
    Menu.buildFromTemplate(createTextEditingMenuTemplate(params)).popup({
      window: win,
    });
  });

  if (app.isPackaged) {
    win.loadFile(path.join(__dirname, "..", "dist", "index.html"));
  } else {
    win.loadURL(DEV_URL);
  }
}

app.whenReady().then(() => {
  createWindow();
  app.on("activate", () => {
    if (BrowserWindow.getAllWindows().length === 0) {
      createWindow();
    }
  });
});

app.on("window-all-closed", () => {
  if (process.platform !== "darwin") {
    app.quit();
  }
});
