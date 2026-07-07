/**
 * 轻量级国际化框架
 * 支持中文(zh-CN)、英语(en-US)、德语(de-DE)
 * 
 * 特性：
 * - 无第三方依赖
 * - 自动检测浏览器语言
 * - 支持localStorage持久化
 * - 支持插值参数
 * - 支持热切换（无需刷新）
 */
class I18n {
    constructor() {
        this.currentLang = this.detectLanguage();
        this.messages = {};
        this.fallbackLang = 'zh-CN';
    }
    
    /**
     * 检测用户语言
     * 优先级：localStorage > 浏览器语言 > 默认中文
     */
    detectLanguage() {
        const supportedLangs = ['zh-CN', 'en-US', 'de-DE'];
        
        const saved = localStorage.getItem('monitor-lang');
        if (saved && supportedLangs.includes(saved)) {
            return saved;
        }
        
        const browserLang = navigator.language || navigator.userLanguage || 'zh-CN';
        
        const langMap = {
            'zh': 'zh-CN',
            'zh-CN': 'zh-CN',
            'zh-Hans': 'zh-CN',
            'zh-Hans-CN': 'zh-CN',
            'zh-TW': 'zh-CN',
            'zh-HK': 'zh-CN',
            'zh-Hant': 'zh-CN',
            'en': 'en-US',
            'en-US': 'en-US',
            'en-GB': 'en-US',
            'en-AU': 'en-US',
            'en-CA': 'en-US',
            'de': 'de-DE',
            'de-DE': 'de-DE',
            'de-AT': 'de-DE',
            'de-CH': 'de-DE',
            'de-LI': 'de-DE'
        };
        
        if (langMap[browserLang]) {
            return langMap[browserLang];
        }
        
        const baseLang = browserLang.split('-')[0];
        if (langMap[baseLang]) {
            return langMap[baseLang];
        }
        
        return 'zh-CN';
    }
    
    /**
     * 初始化i18n
     */
    async init() {
        try {
            await this.loadLanguage(this.currentLang);
            this.applyTranslations();
            this.updateLangSelector();
            this.updateHtmlLang();
            
            // 通知所有监听者语言已加载
            window.dispatchEvent(new CustomEvent('langchange', { 
                detail: { lang: this.currentLang } 
            }));
            
            console.log(`[i18n] Initialized with language: ${this.currentLang}`);
            return true;
        } catch (error) {
            console.error('[i18n] Initialization failed:', error);
            
            if (this.currentLang !== this.fallbackLang) {
                console.log('[i18n] Falling back to:', this.fallbackLang);
                this.currentLang = this.fallbackLang;
                return await this.init();
            }
            
            return false;
        }
    }
    
    /**
     * 加载语言包
     */
    async loadLanguage(lang) {
        const varName = `__i18n_${lang.replace('-', '_')}__`;
        
        if (window[varName]) {
            this.messages = window[varName];
            return;
        }
        
        return new Promise((resolve, reject) => {
            const script = document.createElement('script');
            script.src = `/static/lib/i18n/${lang}.js`;
            script.onload = () => {
                if (window[varName]) {
                    this.messages = window[varName];
                    resolve();
                } else {
                    reject(new Error(`Language pack variable not found: ${varName}`));
                }
            };
            script.onerror = () => reject(new Error(`Failed to load language pack: ${lang}`));
            document.head.appendChild(script);
        });
    }
    
    /**
     * 应用翻译到DOM
     */
    applyTranslations() {
        document.querySelectorAll('[data-i18n]').forEach(el => {
            const key = el.getAttribute('data-i18n');
            const text = this.t(key);
            if (text !== key) {
                el.textContent = text;
            }
        });
        
        document.querySelectorAll('[data-i18n-placeholder]').forEach(el => {
            const key = el.getAttribute('data-i18n-placeholder');
            const text = this.t(key);
            if (text !== key) {
                el.placeholder = text;
            }
        });
        
        document.querySelectorAll('[data-i18n-title]').forEach(el => {
            const key = el.getAttribute('data-i18n-title');
            const text = this.t(key);
            if (text !== key) {
                el.title = text;
            }
        });
        
        document.querySelectorAll('[data-i18n-value]').forEach(el => {
            const key = el.getAttribute('data-i18n-value');
            const text = this.t(key);
            if (text !== key) {
                el.value = text;
            }
        });
        
        const pageTitle = document.querySelector('[data-i18n-page-title]');
        if (pageTitle) {
            const key = pageTitle.getAttribute('data-i18n-page-title');
            const text = this.t(key);
            if (text !== key) {
                document.title = text;
            }
        }
    }
    
    /**
     * 获取翻译文本
     * @param {string} key - 翻译键
     * @param {object} params - 插值参数（可选）
     */
    t(key, params = {}) {
        let text = this.messages[key] || key;
        
        Object.keys(params).forEach(k => {
            text = text.replace(new RegExp(`\\{${k}\\}`, 'g'), params[k]);
        });
        
        return text;
    }
    
    /**
     * 切换语言
     */
    async switchLanguage(lang) {
        if (lang === this.currentLang) return;
        
        const supportedLangs = ['zh-CN', 'en-US', 'de-DE'];
        if (!supportedLangs.includes(lang)) {
            console.error('[i18n] Unsupported language:', lang);
            return;
        }
        
        try {
            localStorage.setItem('monitor-lang', lang);
            
            this.currentLang = lang;
            await this.loadLanguage(lang);
            this.applyTranslations();
            this.updateLangSelector();
            this.updateHtmlLang();
            
            window.dispatchEvent(new CustomEvent('langchange', { 
                detail: { lang: lang } 
            }));
            
            console.log(`[i18n] Language switched to: ${lang}`);
        } catch (error) {
            console.error('[i18n] Language switch failed:', error);
        }
    }
    
    /**
     * 更新语言选择器状态
     */
    updateLangSelector() {
        const selector = document.getElementById('lang-selector');
        if (selector) {
            selector.value = this.currentLang;
        }
    }
    
    /**
     * 更新HTML lang属性
     */
    updateHtmlLang() {
        const htmlEl = document.documentElement;
        if (htmlEl) {
            htmlEl.lang = this.currentLang;
        }
    }
    
    /**
     * 获取当前语言
     */
    getCurrentLang() {
        return this.currentLang;
    }
    
    /**
     * 获取支持的语言列表
     */
    getSupportedLanguages() {
        return [
            { code: 'zh-CN', name: '中文', flag: '🇨🇳' },
            { code: 'en-US', name: 'English', flag: '🇺🇸' },
            { code: 'de-DE', name: 'Deutsch', flag: '🇩🇪' }
        ];
    }
    
    /**
     * 检查是否有翻译
     */
    has(key) {
        return !!this.messages[key];
    }
    
    /**
     * 获取所有翻译键
     */
    getKeys() {
        return Object.keys(this.messages);
    }
}

const i18n = new I18n();

if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', () => i18n.init());
} else {
    i18n.init();
}
