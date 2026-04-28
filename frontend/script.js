marked.setOptions({ breaks: true, gfm: true });

const messagesContainer = document.getElementById('messages');
const typingEl = document.getElementById('typing');
const sendBtn = document.getElementById('sendBtn');
const userInput = document.getElementById('userInput');
const scrollBtn = document.getElementById('scrollBtn');

/* ── Theme toggle ────────────────────────────────────────────────── */
let isDark = true;
function toggleTheme() {
    isDark = !isDark;
    document.documentElement.setAttribute('data-theme', isDark ? 'dark' : 'light');
    document.getElementById('themeToggle').textContent = isDark ? '☀️' : '🌙';
}

/* ── Expandable textarea ─────────────────────────────────────────── */
userInput.addEventListener('input', autoResize);
function autoResize() {
    userInput.style.height = 'auto';
    userInput.style.height = Math.min(userInput.scrollHeight, 180) + 'px';
    userInput.classList.toggle('expanded', userInput.scrollHeight > 58);
}

/* ── Enter to send ───────────────────────────────────────────────── */
userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
    }
});

/* ── Scroll-to-bottom ────────────────────────────────────────────── */
messagesContainer.addEventListener('scroll', () => {
    const atBottom = messagesContainer.scrollHeight - messagesContainer.scrollTop - messagesContainer.clientHeight < 80;
    scrollBtn.classList.toggle('visible', !atBottom);
});

function scrollToBottom() {
    messagesContainer.scrollTo({ top: messagesContainer.scrollHeight, behavior: 'smooth' });
}

/* ── Chip helper ─────────────────────────────────────────────────── */
function fillInput(btn) {
    userInput.value = btn.textContent;
    autoResize();
    userInput.focus();
}

/* ── Send ────────────────────────────────────────────────────────── */
function sendMessage() {
    const question = userInput.value.trim();
    if (question === '') return;

    const wb = document.getElementById('welcomeBlock');
    if (wb) wb.style.display = 'none';

    addMessage(question, 'user');
    userInput.value = '';
    autoResize();
    setLoading(true);

    fetch('https://api.example.com/ai', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question })
    })
        .then(response => response.json())
        .then(data => {
            setLoading(false);
            addMessage(data.answer, 'ai');
        })
        .catch(error => {
            console.error('Errore:', error);
            setLoading(false);
            addMessage('Errore nella comunicazione con il servizio AI.', 'ai');
        });
}

/* ── Add message ─────────────────────────────────────────────────── */
function addMessage(text, sender) {
    const wrap = document.createElement('div');
    wrap.classList.add('message', sender);

    if (sender === 'ai') {
        const chip = document.createElement('div');
        chip.classList.add('ai-chip');
        chip.innerHTML = '<div class="ai-avatar">🍳</div><span class="ai-name">Chef AI</span>';
        wrap.appendChild(chip);
    }

    const bubble = document.createElement('div');
    bubble.classList.add('bubble');

    if (sender === 'ai') {
        bubble.innerHTML = marked.parse(text);
    } else {
        // preserve newlines from textarea
        bubble.innerHTML = text
            .replace(/&/g, '&amp;')
            .replace(/</g, '&lt;')
            .replace(/>/g, '&gt;')
            .replace(/\n/g, '<br>');
    }

    const meta = document.createElement('span');
    meta.classList.add('meta');
    const now = new Date();
    const time = now.getHours().toString().padStart(2, '0') + ':' + now.getMinutes().toString().padStart(2, '0');
    meta.innerHTML = sender === 'user'
        ? `Tu <span class="meta-dot"></span> ${time}`
        : `Chef AI <span class="meta-dot"></span> ${time}`;

    wrap.appendChild(bubble);
    wrap.appendChild(meta);
    messagesContainer.insertBefore(wrap, typingEl);
    scrollToBottom();
}

/* ── Loading ─────────────────────────────────────────────────────── */
function setLoading(active) {
    typingEl.style.display = active ? 'flex' : 'none';
    sendBtn.disabled = active;
    userInput.disabled = active;
    if (active) scrollToBottom();
    else userInput.focus();
}

userInput.focus();