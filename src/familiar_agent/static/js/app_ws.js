/**
 * メインアプリケーションモジュール (WebSocket版)
 */
import { ChatManager } from './chat_ws.js';
import { AnimationManager } from './animation.js';
import { SoundManager } from './sound.js';
import { createSettings } from './settings.js';

// DOM読み込み完了後に初期化
document.addEventListener('DOMContentLoaded', () => {
    // 設定の初期化
    const settings = createSettings(appConfig);
    
    // サウンドマネージャーの初期化
    const soundManager = new SoundManager(settings);
    
    // アニメーションマネージャーの初期化
    const animationManager = new AnimationManager(settings, soundManager);
    
    // チャットマネージャーの初期化（WebSocket版）
    const chatManager = new ChatManager(settings, animationManager);
    
    console.log('Familiar AI Client initialized (WebSocket)');
});
