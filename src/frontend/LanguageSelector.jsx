import React from 'react';
import { useTranslation } from 'react-i18next';
import './App.css';

const LanguageSelector = ({ isOpen }) => {
    const { i18n } = useTranslation();
    const currentLanguage = i18n.language;

    const toggleLanguage = () => {
        const newLanguage = currentLanguage === 'en' ? 'ko' : 'en';
        i18n.changeLanguage(newLanguage);
    };

    const currentFlag = currentLanguage === 'en' ? '🇺🇸' : '🇰🇷';

    return (
        <button
            className={`language-toggle ${isOpen ? 'hidden' : ''}`}
            onClick={toggleLanguage}
            aria-label="Toggle language"
        >
            <img src="/lang-transparent.png" className="icon" alt="Language" />
        </button>
    );
};

export default LanguageSelector;
