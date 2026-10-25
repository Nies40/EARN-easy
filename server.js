const path = require("node:path");
const crypto = require("node:crypto");
const express = require("express");
const Database = require("better-sqlite3");
const bcrypt = require("bcryptjs");
const session = require("express-session");
const SQLiteStore = require("connect-sqlite3")(session);

const app = express();
const port = process.env.PORT || 3000;
const db = new Database(path.join(__dirname, "accounts.db"));
db.pragma("journal_mode = WAL");

db.exec(`
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    username TEXT NOT NULL COLLATE NOCASE UNIQUE,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    phone TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  )
`);

const sessionSecret = process.env.SESSION_SECRET || crypto.randomBytes(32).toString("hex");
if (!process.env.SESSION_SECRET) {
  console.warn("SESSION_SECRET is not set. Sessions will be invalidated when this server restarts.");
}
if (process.env.NODE_ENV === "production") app.set("trust proxy", 1);

app.use(express.json({ limit: "20kb" }));
app.use(session({
  store: new SQLiteStore({ db: "sessions.sqlite", dir: __dirname }),
  name: "easyearn.sid",
  secret: sessionSecret,
  resave: false,
  saveUninitialized: false,
  cookie: {
    httpOnly: true,
    sameSite: "lax",
    secure: process.env.NODE_ENV === "production",
    maxAge: 7 * 24 * 60 * 60 * 1000
  }
}));

// Serve only the public page; keep database and server files private.
app.get("/", (_req, res) => res.sendFile(path.join(__dirname, "Index.html")));
app.get("/Index.html", (_req, res) => res.sendFile(path.join(__dirname, "Index.html")));

app.post("/api/signup", async (req, res) => {
  const { name, username, email, phone, password } = req.body || {};
  if (typeof name !== "string" || !name.trim() || name.length > 100 ||
      typeof username !== "string" || !/^[A-Za-z0-9_]{3,30}$/.test(username) ||
      typeof email !== "string" || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email) || email.length > 254 ||
      typeof phone !== "string" || !/^\+?[0-9]{7,16}$/.test(phone) ||
      typeof password !== "string" || password.length < 8 || password.length > 72) {
    return res.status(400).json({ error: "Please check your details. Passwords must be 8–72 characters." });
  }

  try {
    const passwordHash = await bcrypt.hash(password, 12);
    const result = db.prepare(`
      INSERT INTO users (name, username, email, phone, password_hash)
      VALUES (?, ?, ?, ?, ?)
    `).run(name.trim(), username.trim(), email.trim(), phone.trim(), passwordHash);
    req.session.userId = Number(result.lastInsertRowid);
    res.status(201).json({
      message: "Account created successfully.",
      user: { name: name.trim(), username: username.trim() }
    });
  } catch (error) {
    if (error.code === "SQLITE_CONSTRAINT_UNIQUE") {
      return res.status(409).json({ error: "That username or email is already registered." });
    }
    console.error(error);
    res.status(500).json({ error: "Could not create your account." });
  }
});

app.post("/api/login", async (req, res) => {
  const { username, password } = req.body || {};
  if (typeof username !== "string" || typeof password !== "string" || password.length > 72) {
    return res.status(400).json({ error: "Enter your username and password." });
  }
  const user = db.prepare(
    "SELECT id, name, username, password_hash FROM users WHERE username = ?"
  ).get(username.trim());
  if (!user || !(await bcrypt.compare(password, user.password_hash))) {
    return res.status(401).json({ error: "Incorrect username or password." });
  }
  req.session.regenerate(error => {
    if (error) return res.status(500).json({ error: "Could not start your session." });
    req.session.userId = user.id;
    req.session.save(saveError => {
      if (saveError) return res.status(500).json({ error: "Could not save your session." });
      res.json({ message: "Signed in successfully.", user: { name: user.name, username: user.username } });
    });
  });
});

app.get("/api/me", (req, res) => {
  if (!req.session.userId) return res.status(401).json({ error: "Not signed in." });
  const user = db.prepare("SELECT name, username FROM users WHERE id = ?").get(req.session.userId);
  if (!user) return res.status(401).json({ error: "Not signed in." });
  res.json({ user });
});

app.post("/api/logout", (req, res) => {
  req.session.destroy(error => {
    if (error) return res.status(500).json({ error: "Could not sign out." });
    res.clearCookie("easyearn.sid", { httpOnly: true, sameSite: "lax", secure: process.env.NODE_ENV === "production" });
    res.json({ message: "Signed out." });
  });
});

app.listen(port, () => console.log(`EASYEARN is running at http://localhost:${port}`));
