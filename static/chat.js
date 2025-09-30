let username = localStorage.getItem("username");
let lang = localStorage.getItem("language");

let firstLoad = true;


document.addEventListener('DOMContentLoaded', function () {
  const welcomeScreen = document.getElementById("welcome-screen");
  const username = localStorage.getItem("username");

  if (!username) {
    welcomeScreen.style.display = "flex";
  } else {
    welcomeScreen.style.display = "none";
    document.getElementById("username-display").textContent = username;
  }

  document.getElementById("nameSubmit").addEventListener("click", () => {
    const input = document.getElementById("nameInput").value.trim();
    if (input) {
      localStorage.setItem("username", input);
      location.reload(); // this reloads the page after storing the name
    }
  });

  document.getElementById("nameInput").addEventListener("keypress", e => {
    if (e.key === "Enter") {
      document.getElementById("nameSubmit").click();
    }
  });
});


if (!lang) {
  lang = "en"; // fallback default
  localStorage.setItem("language", lang);
}

// Ensure lowercase for matching, but keep display original
const usernameClean = username.trim().toLowerCase();

async function loadMessages() {
  const res = await fetch(`/messages?lang=${lang}&user=${username}`);
  const data = await res.json();

  const chatbox = document.querySelector(".messages-content");
  chatbox.innerHTML = "";

  data.messages.forEach(msg => {
    const senderClean = msg.from.trim().toLowerCase();
    const isPersonal = senderClean === usernameClean;
  
    const msgDiv = document.createElement("div");
    msgDiv.classList.add("message");
    if (isPersonal) msgDiv.classList.add("message-personal");
    msgDiv.classList.add("new");
  
    const displayName = msg.from.charAt(0).toUpperCase() + msg.from.slice(1);
  
    if (msg.msg_type === "image") {
      msgDiv.innerHTML = `<b>${displayName}</b>: <br><img src="${msg.content}" alt="Uploaded" class="chat-image">`;
    } else {
      msgDiv.innerHTML = `<b>${displayName}</b>: <i>${msg.content}</i>`;
    }
  
    chatbox.appendChild(msgDiv);
  });
  
  const isNearBottom = chatbox.scrollHeight - chatbox.scrollTop <= chatbox.clientHeight + 100;

  // Always scroll on first load
  if (firstLoad || isNearBottom) {
    chatbox.scrollTop = chatbox.scrollHeight;
    firstLoad = false;
  }
  
  
}

async function sendMessage() {
  const messageBox = document.getElementById("message");
  const message = messageBox.value.trim();

  if (message === "") return;
  if (message.toLowerCase() === "/clear") {
    const res = await fetch("/clear", { method: "POST" });
    const data = await res.json();
    
    if (data.status === "cleared") {
      document.querySelector(".messages-content").innerHTML = ""; // Clear display
      document.getElementById("message").value = ""; // Clear the input box
      loadMessages(); 
    }
  
    return;
  }
  
  

  messageBox.value = "";

  await fetch("/send", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      text: message,
      from: username.trim(),
      to_lang: lang.trim()
    })
  });

  loadMessages();
}

// Send on Enter key
document.getElementById("message").addEventListener("keypress", function (e) {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendMessage();
  }
});

// Send on button click
document.querySelector(".message-submit").addEventListener("click", sendMessage);

// Load + auto-refresh
loadMessages();
setInterval(loadMessages, 2000);

// Handle language dropdown click
document.addEventListener('DOMContentLoaded', function () {
  const langOptions = document.querySelectorAll('#language-options li');
  const currentLang = document.getElementById('current-lang');

  const selected = Array.from(langOptions).find(li => li.dataset.lang === lang);
  if (selected) currentLang.textContent = selected.textContent;

  langOptions.forEach(li => {
    li.addEventListener('click', () => {
      const selectedLang = li.dataset.lang;
      localStorage.setItem('language', selectedLang);
      location.reload(); // Refresh to load new language
    });
  });
});

document.addEventListener('DOMContentLoaded', function () {

  let username = localStorage.getItem('username');
  
  document.getElementById('username-display').textContent = username;

  const lang = localStorage.getItem('language') || 'en';
  const langOptions = document.querySelectorAll('#language-options li');
  const currentLang = document.getElementById('current-lang');

  const selected = Array.from(langOptions).find(li => li.dataset.lang === lang);
  if (selected) currentLang.textContent = selected.textContent;

  langOptions.forEach(li => {
    li.addEventListener('click', () => {
      const selectedLang = li.dataset.lang;
      localStorage.setItem('language', selectedLang);
      currentLang.textContent = li.textContent;
      document.getElementById('language-toggle').checked = false; 
      location.reload(); 
    });
  });

  document.getElementById("message").addEventListener("keypress", function (e) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      sendMessage();
    }
  });
});

document.addEventListener("DOMContentLoaded", () => {
  const messagesContent = document.querySelector(".messages-content");
  const uploadBtn = document.getElementById("upload-btn");

  // Create hidden file input dynamically
  const imageInput = document.createElement("input");
  imageInput.type = "file";
  imageInput.accept = "image/*";
  imageInput.style.display = "none";
  document.body.appendChild(imageInput);

  // Trigger file input
  uploadBtn.addEventListener("click", () => {
    imageInput.click();
  });

  // When user selects an image
  imageInput.addEventListener("change", async () => {
    const file = imageInput.files[0];
    if (!file) return;

    const formData = new FormData();
    formData.append("image", file);

    try {
      const response = await fetch("/upload_image", {
        method: "POST",
        body: formData,
      });

      const data = await response.json();
      if (data.status === "ok") {
        const imgUrl = data.url;

        // Display image in chat
        const msg = document.createElement("div");
        msg.className = "message message-personal";
        msg.innerHTML = `<img src="${imgUrl}" alt="Uploaded" class="chat-image">`;
        messagesContent.appendChild(msg);

        messagesContent.scrollTop = messagesContent.scrollHeight;
      } else {
        alert("Upload failed: " + data.message);
      }
    } catch (err) {
      console.error("Upload error", err);
      alert("Error uploading image.");
    }

    // Reset input
    imageInput.value = "";
  });
});
