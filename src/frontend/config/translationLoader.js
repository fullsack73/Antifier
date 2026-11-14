import enTranslation from '../locales/en/translation.json';
import koTranslation from '../locales/ko/translation.json';

export const loadTranslations = (i18n) => {
    i18n.addResourceBundle('en', 'translation', enTranslation, true, true);
    i18n.addResourceBundle('ko', 'translation', koTranslation, true, true);
    // Refresh mounted translations when locale files change during development.
    if (import.meta.hot) {
        import.meta.hot.accept(['../locales/en/translation.json', '../locales/ko/translation.json'], modules => {
            modules.forEach((module, index) => {
                if (module) i18n.addResourceBundle(index === 0 ? 'en' : 'ko', 'translation', module.default, true, true);
            });
            i18n.emit('languageChanged', i18n.language);
        });
    }
};
