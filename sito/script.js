const messagesContainer = document.getElementById('messages');
const typingEl = document.getElementById('typing');
const sendBtn = document.getElementById('sendBtn');
const userInput = document.getElementById('userInput');

userInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') sendMessage();
});

function fillInput(btn) {
    userInput.value = btn.textContent;
    userInput.focus();
}

function sendMessage() {
    const question = userInput.value.trim();
    if (question === '') return;

    // hide welcome on first message
    const wb = document.getElementById('welcomeBlock');
    if (wb) wb.style.display = 'none';

    addMessage(question, 'user');
    userInput.value = '';
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
    bubble.textContent = text;

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
    messagesContainer.scrollTop = messagesContainer.scrollHeight;
}

function setLoading(active) {
    typingEl.style.display = active ? 'flex' : 'none';
    sendBtn.disabled = active;
    userInput.disabled = active;
    if (active) messagesContainer.scrollTop = messagesContainer.scrollHeight;
    else userInput.focus();
}

userInput.focus();