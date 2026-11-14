import { expect, it } from 'vitest'
import { createInstance } from 'i18next'
import { loadTranslations } from '../src/frontend/config/translationLoader.js'

it('loads readable optimizer tab labels in both languages', async () => {
  const i18n = createInstance()
  await i18n.init({ lng: 'en', resources: {} })
  loadTranslations(i18n)
  expect(i18n.t('optimizer.settingsTabs.allocation')).toBe('Allocation')
  await i18n.changeLanguage('ko')
  expect(i18n.t('optimizer.settingsTabs.allocation')).toBe('최적화 조건')
  expect(i18n.t('candidateSearch.enabled')).toBe('후보 탐색 사용')
})
