import { useEffect } from 'react';
import { useTranslation } from 'react-i18next';
import './App.css';

const LanguageSelector = ({ isOpen }) => {
    const { i18n, t } = useTranslation();
    const currentLanguage = i18n.language;

    useEffect(() => {
        document.documentElement.lang = currentLanguage === 'ko' ? 'ko' : 'en';
    }, [currentLanguage]);

    const toggleLanguage = () => {
        const newLanguage = currentLanguage === 'en' ? 'ko' : 'en';
        i18n.changeLanguage(newLanguage);
    };

    return (
        <button
            className={`language-toggle ${isOpen ? 'hidden' : ''}`}
            type="button"
            onClick={toggleLanguage}
            aria-label={t('common.toggleLanguage', 'Toggle language')}
        >
            <img src="/lang-transparent.png" className="icon" alt="" />
        </button>
    );
};

export default LanguageSelector;
