/**
 * チャット機能モジュール (SocketIO版)
 * メッセージの送受信とUI更新を管理
 */
export class ChatManager {
    constructor(settings, animationManager) {
        this.settings = settings;
        this.animationManager = animationManager;
        this.output = document.getElementById('output');
        this.input = document.getElementById('input');
        this.socket = null;
        this.currentAiLine = null;
        this.isProcessing = false;

        this.initSocket();
        this.initEventListeners();
    }

    // SocketIO接続初期化
    initSocket() {
        this.socket = io();

        this.socket.on('connect', () => {
            console.log('Connected to server');
        });

        this.socket.on('disconnect', () => {
            console.log('Disconnected from server');
        });

        // ユーザーメッセージ表示（サーバーからブロードキャスト）
        this.socket.on('user_message', (data) => {
            this.addLine(data.message, 'user');
        });

        // AIのテキストチャンクをリアルタイム表示
        this.socket.on('text_chunk', (data) => {
            if (!this.currentAiLine) {
                this.startAiLine();
            }
            this.appendToAiLine(data.chunk);
            // タイプライター音を再生（チャンクごと）
            this.animationManager.playBeep();
        });

        // ツール実行表示
        this.socket.on('action', (data) => {
            this.addActionLine(data);
        });

        // レスポンス完了
        this.socket.on('response_complete', (data) => {
            this.isProcessing = false;
            this.currentAiLine = null;
            this.input.disabled = false;
            this.input.focus();
            this.animationManager.stopTalking();
        });

        // エラー
        this.socket.on('error', (data) => {
            this.addLine(`ERROR: ${data.message}`, 'system');
            this.isProcessing = false;
            this.currentAiLine = null;
            this.input.disabled = false;
            this.input.focus();
            this.animationManager.stopTalking();
        });

        // 履歴クリア
        this.socket.on('history_cleared', () => {
            this.output.innerHTML = '<div class="line system">&gt; SYSTEM: History cleared</div>';
        });
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
                this.socket.emit('clear_history');
            }
        });
    }

    // メッセージ送信
    async sendMessage(message) {
        if (this.isProcessing) return;

        this.isProcessing = true;
        this.input.disabled = true;

        // アバターを話している状態に
        this.animationManager.startTalking();

        // SocketIOで送信
        this.socket.emit('chat', { message });
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
