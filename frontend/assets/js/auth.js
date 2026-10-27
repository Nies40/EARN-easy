"use strict";

const signupForm = document.getElementById("signupForm");
const loginForm = document.getElementById("loginForm");
const accountPanel = document.getElementById("accountPanel");
const authSwitch = document.querySelector(".auth-switch");
const signupMessage = document.getElementById("message");
const loginMessage = document.getElementById("loginMessage");
const accountMessage = document.getElementById("accountMessage");
const password = document.getElementById("password");
const confirmPassword = document.getElementById("confirmPassword");

function setMessage(element, text, state = "pending") {
    element.textContent = text;
    element.dataset.state = state;
}

function setBusy(button, busy) {
    button.disabled = busy;
    button.setAttribute("aria-busy", String(busy));
}

async function request(path, body) {
    let response;
    try {
        response = await fetch(`/api${path}`, {
            method: body === undefined ? "GET" : "POST",
            credentials: "same-origin",
            headers:
                body === undefined
                    ? {}
                    : { "Content-Type": "application/json" },
            body: body === undefined ? undefined : JSON.stringify(body),
        });
    } catch {
        throw new Error("Could not reach the server. Please try again.");
    }
    const result = await response.json().catch(() => ({}));
    if (!response.ok) {
        const detail = result.details?.[0];
        const message = detail
            ? `${detail.field}: ${detail.message}`
            : result.error;
        const error = new Error(
            message || "The request could not be completed.",
        );
        error.status = response.status;
        throw error;
    }
    return result;
}

function showMode(mode, focus = false) {
    const signingUp = mode === "signup";
    accountPanel.hidden = true;
    authSwitch.hidden = false;
    signupForm.hidden = !signingUp;
    loginForm.hidden = signingUp;
    document
        .getElementById("showSignup")
        .setAttribute("aria-pressed", String(signingUp));
    document
        .getElementById("showLogin")
        .setAttribute("aria-pressed", String(!signingUp));
    document.getElementById("pageHeading").textContent = signingUp
        ? "Create your account"
        : "Welcome back";
    document.getElementById("pageDescription").textContent = signingUp
        ? "Fill in your details to get started for free."
        : "Sign in to your Easyearn account.";
    setMessage(signupMessage, "");
    setMessage(loginMessage, "");
    setMessage(accountMessage, "");
    if (focus)
        document.getElementById(signingUp ? "name" : "loginIdentifier").focus();
}

function showAccount(user) {
    authSwitch.hidden = true;
    signupForm.hidden = true;
    loginForm.hidden = true;
    accountPanel.hidden = false;
    document.getElementById("pageHeading").textContent = "Your account";
    document.getElementById("pageDescription").textContent =
        "You are signed in to Easyearn.";
    document.getElementById("accountWelcome").textContent =
        `Welcome, ${user.name}!`;
    document.getElementById("accountEmail").textContent = user.email;
    document.querySelector(".account-note").textContent = user.email_verified
        ? "Your email is verified."
        : "Verify your email to unlock dashboard access.";
    setMessage(accountMessage, "");
}

document
    .getElementById("showSignup")
    .addEventListener("click", () => showMode("signup", true));
document
    .getElementById("showLogin")
    .addEventListener("click", () => showMode("login", true));

document.querySelectorAll(".toggle").forEach((button) => {
    button.addEventListener("click", () => {
        const field = document.getElementById(button.dataset.target);
        const show = field.type === "password";
        field.type = show ? "text" : "password";
        button.setAttribute("aria-pressed", String(show));
        button.setAttribute(
            "aria-label",
            `${show ? "Hide" : "Show"} ${
                field.id === "password" ? "password" : "confirm password"
            }`,
        );
    });
});

signupForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    if (!signupForm.reportValidity()) return;
    if (new TextEncoder().encode(password.value).length > 72) {
        setMessage(
            signupMessage,
            "Password must be at most 72 UTF-8 bytes.",
            "error",
        );
        password.focus();
        return;
    }
    if (password.value !== confirmPassword.value) {
        setMessage(signupMessage, "Your passwords do not match.", "error");
        confirmPassword.focus();
        return;
    }

    const phone = document.getElementById("phone").value.trim();
    const countryCode = document.getElementById("countryCode").value;
    const digits = phone.replace(/[\s().-]/g, "");
    if (
        phone &&
        (!/^\d+$/.test(digits) ||
            digits.length < 7 ||
            (countryCode + digits).length > 17)
    ) {
        setMessage(
            signupMessage,
            "Please enter a valid phone number.",
            "error",
        );
        document.getElementById("phone").focus();
        return;
    }

    const button = signupForm.querySelector(".submit");
    setBusy(button, true);
    setMessage(signupMessage, "Creating your account…");
    try {
        const result = await request("/signup", {
            name: document.getElementById("name").value.trim(),
            username: document.getElementById("username").value.trim() || null,
            email: document.getElementById("email").value.trim(),
            phone: phone ? countryCode + digits : null,
            password: password.value,
        });
        signupForm.reset();
        showAccount(result.user);
    } catch (error) {
        setMessage(signupMessage, error.message, "error");
    } finally {
        setBusy(button, false);
    }
});

loginForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    const button = loginForm.querySelector(".submit");
    setBusy(button, true);
    setMessage(loginMessage, "Signing in…");
    try {
        const result = await request("/login", {
            identifier: document.getElementById("loginIdentifier").value.trim(),
            password: document.getElementById("loginPassword").value,
        });
        loginForm.reset();
        showAccount(result.user);
    } catch (error) {
        setMessage(loginMessage, error.message, "error");
    } finally {
        setBusy(button, false);
    }
});

document
    .getElementById("logoutButton")
    .addEventListener("click", async (event) => {
        const button = event.currentTarget;
        setBusy(button, true);
        try {
            await request("/logout", {});
            signupForm.reset();
            loginForm.reset();
            showMode("login", true);
        } catch (error) {
            setMessage(accountMessage, error.message, "error");
        } finally {
            setBusy(button, false);
        }
    });

[password, confirmPassword].forEach((field) => {
    field.addEventListener("input", () => setMessage(signupMessage, ""));
});

request("/me")
    .then((result) => showAccount(result.user))
    .catch((error) => {
        if (error.status !== 401)
            setMessage(signupMessage, error.message, "error");
    });
