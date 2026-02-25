/**
 * チャット機能モジュール (生WebSocket版)
 * メッセージの送受信とUI更新を管理
 */
export class ChatManager {
    constructor(settings, animationManager) {
        this.settings = settings;
        this.animationManager = animationManager;
        this.output = document.getElementById('output');
        this.input = document.getElementById('input');
        this.ws = null;
        this.reconnectInterval = 5000;
        this.currentAiLine = null;
        this.isProcessing = false;

        this.initWebSocket();
        this.initEventListeners();
    }

    // WebSocket接続初期化
    initWebSocket() {
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws`;

        console.log(`Connecting to WebSocket: ${wsUrl}`);
        this.ws = new WebSocket(wsUrl);

        this.ws.onopen = () => {
            console.log('WebSocket connected');
            this.addLine('Connected to server', 'system');
        };

        this.ws.onclose = () => {
            console.log('WebSocket disconnected');
            this.addLine('Disconnected from server', 'system');
            // Reconnect after delay
            setTimeout(() => this.initWebSocket(), this.reconnectInterval);
        };

        this.ws.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.addLine('Connection error', 'system');
        };

        this.ws.onmessage = (event) => {
            this.handleMessage(JSON.parse(event.data));
        };
    }

    // メッセージハンドリング
    handleMessage(data) {
        switch (data.type) {
            case 'connected':
                console.log('Connected:', data.data);
                break;

            case 'user_message':
                this.addLine(data.data.message, 'user');
                break;

            case 'text_chunk':
                if (!this.currentAiLine) {
                    this.startAiLine();
                }
                this.appendToAiLine(data.data.chunk);
                // タイプライター音を再生（チャンクごと）
                this.animationManager.playBeep();
                break;

            case 'action':
                this.addActionLine(data.data);
                break;

            case 'response_complete':
                this.isProcessing = false;
                this.currentAiLine = null;
                this.input.disabled = false;
                this.input.focus();
                this.animationManager.stopTalking();
                break;

            case 'error':
                this.addLine(`ERROR: ${data.data.message}`, 'system');
                this.isProcessing = false;
                this.currentAiLine = null;
                this.input.disabled = false;
                this.input.focus();
                this.animationManager.stopTalking();
                break;

            case 'history_cleared':
                this.output.innerHTML = '<div class="line system">&gt; SYSTEM: History cleared</div>';
                break;

            case 'status':
                console.log('Status:', data.data.message);
                break;

            default:
                console.log('Unknown message type:', data.type);
        }
    }

    // イベントリスナー初期化
    initEventListeners() {
        this.input.addEventListener('keypress', async (e) => {
            if (e.key === 'Enter' && this.input.value.trim() && !this.isProcessing) {
                const message = this.input.value.trim();
                this.input.value = '';
                await this.sendMessage(message);
            }
        });

        // /clear コマンド
        this.input.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' && this.input.value.trim() === '/clear') {
                e.preventDefault();
                this.input.value = '';
                this.sendCommand('clear_history');
            }
        });
    }

    // メッセージ送信
    async sendMessage(message) {
        if (this.isProcessing || this.ws.readyState !== WebSocket.OPEN) return;

        this.isProcessing = true;
        this.input.disabled = true;

        // アバターを話している状態に
        this.animationManager.startTalking();

        // WebSocketで送信
        this.ws.send(JSON.stringify({
            type: 'chat',
            data: { message }
        }));
    }

    // コマンド送信
    sendCommand(command) {
        if (this.ws.readyState !== WebSocket.OPEN) return;

        this.ws.send(JSON.stringify({
            type: command,
            data: null
        }));
    }

    // AIレスポンス行を開始
    startAiLine() {
        const line = document.createElement('div');
        line.className = 'line ai';
        line.innerHTML = `<span class="ai-prompt">${this.settings.avatarName}&gt;</span> <span class="ai-text"></span>`;
        this.output.appendChild(line);
        this.currentAiLine = line.querySelector('.ai-text');
        this.scrollToBottom();
    }

    // AI行にテキストを追加
    appendToAiLine(text) {
        if (this.currentAiLine) {
            this.currentAiLine.textContent += text;
            this.scrollToBottom();
        }
    }

    // アクション表示行を追加
    addActionLine(data) {
        const line = document.createElement('div');
        line.className = 'line action';
        line.style.color = '#888';
        line.style.fontStyle = 'italic';
        line.innerHTML = `<span class="action-icon">${data.icon || '⚙️'}</span> ${data.label || data.name}`;
        this.output.appendChild(line);
        this.scrollToBottom();
    }

    // メッセージを画面に追加
    async addLine(text, type) {
        const line = document.createElement('div');
        line.className = 'line ' + type;

        if (type === 'user') {
            line.innerHTML = `<span class="user-prompt">${this.settings.companionName || 'USER'}&gt;</span> ${text}`;
            this.output.appendChild(line);
            this.scrollToBottom();
        } else if (type === 'ai') {
            // AIメッセージ（完全版を表示）
            line.innerHTML = `<span class="ai-prompt">${this.settings.avatarName}&gt;</span> <span class="ai-text">${text}</span>`;
            this.output.appendChild(line);
            this.scrollToBottom();
        } else {
            // system メッセージなど
            line.textContent = text;
            this.output.appendChild(line);
            this.scrollToBottom();
        }
    }

    // チャットエリアを最下部にスクロール
    scrollToBottom() {
        this.output.scrollTop = this.output.scrollHeight;
    }
}
