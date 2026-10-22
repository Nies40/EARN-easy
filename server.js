const { createServer } = require("node:http");
const { readFile } = require("node:fs/promises");
const { join } = require("node:path");
const { randomBytes, scryptSync } = require("node:crypto");
const { DatabaseSync } = require("node:sqlite");

const PORT = Number(process.env.PORT || 3000);
const ROOT = __dirname;
const db = new DatabaseSync(join(ROOT, "easyearn.sqlite"));
db.exec(`
  PRAGMA journal_mode = WAL;
  PRAGMA foreign_keys = ON;
  CREATE TABLE IF NOT EXISTS users (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    name TEXT NOT NULL,
    email TEXT NOT NULL COLLATE NOCASE UNIQUE,
    phone TEXT NOT NULL,
    password_hash TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
  );
`);
const insertUser = db.prepare(`INSERT INTO users (name, email, phone, password_hash) VALUES (?, ?, ?, ?)`);

function sendJson(response, status, data) {
  response.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Content-Type-Options": "nosniff"
  });
  response.end(JSON.stringify(data));
}

async function readJson(request) {
  let body = "";
  for await (const chunk of request) {
    body += chunk;
    if (body.length > 16_384) throw new Error("Request is too large.");
  }
  return JSON.parse(body);
}

const server = createServer(async (request, response) => {
  const url = new URL(request.url, `http://${request.headers.host || "localhost"}`);

  if (request.method === "POST" && url.pathname === "/api/signup") {
    let data;
    try {
      data = await readJson(request);
    } catch {
      return sendJson(response, 400, { error: "Please submit valid form data." });
    }

    const name = typeof data.name === "string" ? data.name.trim() : "";
    const email = typeof data.email === "string" ? data.email.trim().toLowerCase() : "";
    const phone = typeof data.phone === "string" ? data.phone.trim() : "";
    const password = typeof data.password === "string" ? data.password : "";
    if (name.length < 2 || name.length > 100) return sendJson(response, 400, { error: "Enter a name between 2 and 100 characters." });
    if (email.length > 254 || !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) return sendJson(response, 400, { error: "Enter a valid email address." });
    if (!/^\+[1-9]\d{7,14}$/.test(phone)) return sendJson(response, 400, { error: "Enter a valid phone number." });
    if (password.length < 8 || Buffer.byteLength(password, "utf8") > 1024) return sendJson(response, 400, { error: "Password must be at least 8 characters." });

    const salt = randomBytes(16).toString("hex");
    const passwordHash = `scrypt$${salt}$${scryptSync(password, salt, 64).toString("hex")}`;
    try {
      insertUser.run(name, email, phone, passwordHash);
      return sendJson(response, 201, { message: "Account created successfully. You can now sign in." });
    } catch (error) {
      if (String(error.message).includes("UNIQUE constraint failed")) return sendJson(response, 409, { error: "An account with that email already exists." });
      console.error("Could not save signup:", error.message);
      return sendJson(response, 500, { error: "Could not create your account. Please try again." });
    }
  }

  if (request.method === "GET" && (url.pathname === "/" || url.pathname === "/Index.html")) {
    try {
      const html = await readFile(join(ROOT, "Index.html"));
      response.writeHead(200, { "Content-Type": "text/html; charset=utf-8", "X-Content-Type-Options": "nosniff" });
      return response.end(html);
    } catch {
      return sendJson(response, 500, { error: "The signup page could not be loaded." });
    }
  }
  sendJson(response, 404, { error: "Not found." });
});

server.listen(PORT, () => console.log(`EASYEARN signup is running at http://localhost:${PORT}`));
