/**
 * アニメーション管理モジュール
 * タイプライター効果、日本語音節に基づく口パクアニメーション、瞬きを管理
 */

/**
 * 日本語テキストの音節解析クラス
 */
class JapanesePhonemeAnalyzer {
    constructor() {
        // 母音パターン（口を開くタイミング）
        this.vowels = /[あいうえおアイウエオぁぃぅぇぉァィゥェォ]/;
        // 長音（母音と同様に扱う）
        this.longVowel = /[ー～]/;
        // 促音（短く口を開く）
        this.sokuon = /っッ/;
        // 撥音（鼻音、口は閉じたまま）
        this.hatsuon = /んン/;
        // 句読点や空白（停止）
        this.pause = /[、。！？\.\,\?\!\s]/;
        // 英文字の母音
        this.latinVowels = /[aeiouAEIOU]/;
    }

    /**
     * テキストを解析して音節情報の配列を返す
     * @param {string} text - 解析するテキスト
     * @returns {Array<{char: string, type: string, duration: number}>} 音節情報
     */
    analyze(text) {
        const phonemes = [];
        
        for (let i = 0; i < text.length; i++) {
            const char = text[i];
            const info = this.getPhonemeInfo(char);
            phonemes.push(info);
        }
        
        return phonemes;
    }

    /**
     * 文字の音節情報を取得
     * @param {string} char - 1文字
     * @returns {{char: string, type: string, duration: number}} 音節情報
     */
    getPhonemeInfo(char) {
        if (this.vowels.test(char)) {
            return { char, type: 'vowel', duration: 1.0 };
        }
        if (this.longVowel.test(char)) {
            return { char, type: 'long_vowel', duration: 0.8 };
        }
        if (this.sokuon.test(char)) {
            return { char, type: 'sokuon', duration: 0.3 };
        }
        if (this.hatsuon.test(char)) {
            return { char, type: 'hatsuon', duration: 0.5 }; // んは口を閉じる
        }
        if (this.pause.test(char)) {
            return { char, type: 'pause', duration: 0.2 };
        }
        if (this.latinVowels.test(char)) {
            return { char, type: 'vowel', duration: 0.8 };
        }
        // 子音やその他の文字
        return { char, type: 'consonant', duration: 0.4 };
    }

    /**
     * 口を開けるべきか判定
     * @param {string} type - 音節タイプ
     * @returns {boolean} 口を開けるかどうか
     */
    shouldOpenMouth(type) {
        return type === 'vowel' || type === 'long_vowel' || type === 'sokuon';
    }
}

export class AnimationManager {
    constructor(settings, soundManager) {
        this.settings = settings;
        this.soundManager = soundManager;
        this.avatarImg = document.getElementById('avatar-img');
        this.output = document.getElementById('output');
        
        // 音節解析器
        this.phonemeAnalyzer = new JapanesePhonemeAnalyzer();
        
        // アニメーション制御
        this.isTalking = false;
        this.currentMouthOpen = false;
        this.currentEyesOpen = true;
        
        // 瞬き制御
        this.blinkInterval = null;
        this.isBlinking = false;
        this.nextBlinkTime = 3000;
        
        // 瞬き開始
        this.startBlinking();
    }

    /**
     * キャラクター画像を更新
     * @param {boolean} eyesOpen - 目が開いているか
     * @param {boolean} mouthOpen - 口が開いているか
     */
    updateCharacterImage(eyesOpen = true, mouthOpen = false) {
        this.currentEyesOpen = eyesOpen;
        this.currentMouthOpen = mouthOpen;
        this.avatarImg.src = this.settings.getCharacterImagePath(eyesOpen, mouthOpen);
    }

    // ==================== 瞬きアニメーション ====================

    /**
     * 瞬きアニメーションを開始
     */
    startBlinking() {
        if (this.blinkInterval) {
            clearTimeout(this.blinkInterval);
        }
        
        const scheduleNextBlink = () => {
            // ランダムな間隔（2秒〜6秒）
            this.nextBlinkTime = 2000 + Math.random() * 4000;
            
            this.blinkInterval = setTimeout(() => {
                this.performBlink();
                scheduleNextBlink();
            }, this.nextBlinkTime);
        };
        
        scheduleNextBlink();
    }

    /**
     * 瞬きを実行
     */
    async performBlink() {
        if (this.isBlinking) return;
        
        this.isBlinking = true;
        
        // 目を閉じる（口の状態は維持）
        this.updateCharacterImage(false, this.currentMouthOpen);
        
        // 150ms後に目を開く
        await this.sleep(150);
        
        this.isBlinking = false;
        this.updateCharacterImage(true, this.currentMouthOpen);
    }

    /**
     * 瞬きを停止
     */
    stopBlinking() {
        if (this.blinkInterval) {
            clearTimeout(this.blinkInterval);
            this.blinkInterval = null;
        }
    }

    // ==================== 口パクアニメーション ====================

    /**
     * 日本語音節に基づく口パクアニメーション
     * @param {Array} phonemes - 音節情報の配列
     * @param {number} baseDelay - 基本の文字表示遅延（ms）
     */
    async animateMouthByPhonemes(phonemes, baseDelay) {
        for (let i = 0; i < phonemes.length; i++) {
            const phoneme = phonemes[i];
            const shouldOpen = this.phonemeAnalyzer.shouldOpenMouth(phoneme.type);
            
            // 口の状態を更新
            this.updateCharacterImage(this.currentEyesOpen, shouldOpen);
            
            // 音節の長さに応じた待機
            const duration = baseDelay * phoneme.duration;
            await this.sleep(duration);
            
            // 口を閉じる（次の文字がすぐに来る場合は短く）
            if (i < phonemes.length - 1 && !this.phonemeAnalyzer.shouldOpenMouth(phonemes[i + 1].type)) {
                this.updateCharacterImage(this.currentEyesOpen, false);
            }
        }
    }

    // ==================== タイプライター効果 ====================

    /**
     * タイプライター効果でテキストを表示
     * @param {HTMLElement} element - テキストを表示する要素
     * @param {string} text - 表示するテキスト
     * @returns {Promise<void>}
     */
    typeWriter(element, text) {
        return new Promise((resolve) => {
            this.isTalking = true;
            
            // 音節解析
            const phonemes = this.phonemeAnalyzer.analyze(text);
            
            let charIndex = 0;
            let phonemeIndex = 0;
            
            const typeNext = async () => {
                if (charIndex >= text.length) {
                    // 完了時
                    this.isTalking = false;
                    this.updateCharacterImage(true, false); // 目開き、口閉じ
                    resolve();
                    return;
                }
                
                // 現在の音節を取得
                const phoneme = phonemes[phonemeIndex] || { type: 'consonant', duration: 0.4 };
                
                // 文字を表示
                element.textContent += text[charIndex];
                this.output.scrollTop = this.output.scrollHeight;
                
                // 音を鳴らす（空白・改行以外）
                if (text[charIndex] !== ' ' && text[charIndex] !== '\n') {
                    this.soundManager.playTypeSound();
                }
                
                // 口パク制御
                const shouldOpen = this.phonemeAnalyzer.shouldOpenMouth(phoneme.type);
                this.updateCharacterImage(this.currentEyesOpen, shouldOpen);
                
                charIndex++;
                phonemeIndex++;
                
                // 次の音節を確認
                const nextPhoneme = phonemes[phonemeIndex];
                if (nextPhoneme && !this.phonemeAnalyzer.shouldOpenMouth(nextPhoneme.type)) {
                    // 次が子音や停止の場合は口を閉じる予約
                    setTimeout(() => {
                        if (this.isTalking) {
                            this.updateCharacterImage(this.currentEyesOpen, false);
                        }
                    }, this.settings.typewriterDelay * 0.3);
                }
                
                // 音節の長さに応じた遅延
                const delay = this.settings.typewriterDelay * phoneme.duration;
                setTimeout(typeNext, delay);
            };
            
            typeNext();
        });
    }

    /**
     * シンプルな口パクアニメーション（後方互換性用）
     */
    startMouthAnimation() {
        // 新しい実装では使用しない
    }

    /**
     * 口パクアニメーション停止
     */
    stopMouthAnimation() {
        this.isTalking = false;
        this.updateCharacterImage(true, false);
    }

    // ==================== SocketIO用リアルタイム制御 ====================

    /**
     * 話し始め（SocketIOストリーミング開始時）
     */
    startTalking() {
        this.isTalking = true;
        this.updateCharacterImage(true, true); // 目開き、口開き
    }

    /**
     * 話し終わり（SocketIOストリーミング終了時）
     */
    stopTalking() {
        this.isTalking = false;
        this.updateCharacterImage(true, false); // 目開き、口閉じ
    }

    /**
     * タイプ音を再生（チャンクごとに呼ばれる）
     */
    playBeep() {
        if (!this.isTalking) {
            this.startTalking();
        }
        // 簡易的な口パク（ランダムで口を開閉）
        const shouldOpen = Math.random() > 0.3;
        this.updateCharacterImage(this.currentEyesOpen, shouldOpen);
        // 音を鳴らす
        this.soundManager.playTypeSound();
    }

    /**
     * ユーティリティ：指定時間待機
     * @param {number} ms - 待機時間（ミリ秒）
     * @returns {Promise<void>}
     */
    sleep(ms) {
        return new Promise(resolve => setTimeout(resolve, ms));
    }

    /**
     * アニメーションを破棄（クリーンアップ）
     */
    dispose() {
        this.stopBlinking();
        this.isTalking = false;
    }
}
