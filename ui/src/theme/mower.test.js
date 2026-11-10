import { describe, expect, it } from 'vitest'
import { darkTheme, lightTheme } from 'naive-ui'

import {
  mowerDarkCssVariables,
  mowerDarkThemeOverrides,
  mowerLightCssVariables,
  mowerLightThemeOverrides
} from './mower'

const nativeCommonTokens = [
  'primaryColor',
  'primaryColorHover',
  'primaryColorPressed',
  'primaryColorSuppl',
  'successColor',
  'successColorHover',
  'successColorPressed',
  'successColorSuppl',
  'warningColor',
  'warningColorHover',
  'warningColorPressed',
  'warningColorSuppl',
  'errorColor',
  'errorColorHover',
  'errorColorPressed',
  'errorColorSuppl',
  'infoColor',
  'infoColorHover',
  'infoColorPressed',
  'infoColorSuppl',
  'bodyColor',
  'cardColor',
  'modalColor',
  'popoverColor',
  'inputColor',
  'actionColor',
  'hoverColor',
  'pressedColor',
  'borderColor',
  'dividerColor',
  'tableColor',
  'tableHeaderColor',
  'tableColorStriped',
  'tabColor',
  'boxShadow1',
  'boxShadow2',
  'boxShadow3'
]

const requiredThemeSections = [
  'Layout',
  'Button',
  'Card',
  'Dialog',
  'Modal',
  'Drawer',
  'Input',
  'Checkbox',
  'Radio',
  'Switch',
  'Select',
  'AutoComplete',
  'Tag',
  'Popover',
  'Dropdown',
  'Tooltip',
  'Message',
  'Notification',
  'Alert',
  'Divider',
  'Collapse',
  'DataTable',
  'DatePicker',
  'List',
  'Slider',
  'Table',
  'Tabs',
  'TimePicker',
  'Upload'
]

const themes = [
  [
    'light',
    lightTheme,
    mowerLightThemeOverrides,
    mowerLightCssVariables,
    { color: 'rgba(42, 48, 60, 0.92)', textColor: '#f5f7fb' }
  ],
  [
    'dark',
    darkTheme,
    mowerDarkThemeOverrides,
    mowerDarkCssVariables,
    { color: '#4a5268', textColor: '#eceff4' }
  ]
]

describe.each(themes)('Mower %s theme', (_mode, naiveTheme, mowerTheme, cssVariables, tooltip) => {
  it('defines a complete Nord palette while keeping Naive UI font defaults', () => {
    for (const token of nativeCommonTokens) {
      expect(mowerTheme.common[token], `common.${token}`).toEqual(expect.any(String))
    }
    expect(mowerTheme.common).not.toHaveProperty('fontFamily')
    expect(mowerTheme.common).not.toHaveProperty('fontFamilyMono')
  })

  it('covers every visual component used by the frontend', () => {
    expect(Object.keys(mowerTheme)).toEqual(expect.arrayContaining(requiredThemeSections))
  })

  it('only overrides supported Naive UI theme keys', () => {
    for (const [section, values] of Object.entries(mowerTheme)) {
      const validValues =
        section === 'common' ? naiveTheme.common : naiveTheme[section]?.self?.(naiveTheme.common)
      expect(validValues, `missing Naive UI theme section ${section}`).toBeTruthy()

      const { peers = {}, ...selfValues } = values
      for (const [key, value] of Object.entries(selfValues)) {
        expect(validValues, `${section}.${key}`).toHaveProperty(key)
        expect(value, `${section}.${key}`).not.toBeUndefined()
      }

      for (const [peer, peerValues] of Object.entries(peers)) {
        const validPeerValues = naiveTheme[section]?.peers?.[peer]?.self?.(naiveTheme.common)
        expect(validPeerValues, `missing Naive UI peer ${section}.peers.${peer}`).toBeTruthy()
        for (const [key, value] of Object.entries(peerValues)) {
          expect(validPeerValues, `${section}.peers.${peer}.${key}`).toHaveProperty(key)
          expect(value, `${section}.peers.${peer}.${key}`).not.toBeUndefined()
        }
      }
    }
  })

  it('uses progressively larger radii for larger components', () => {
    expect(mowerTheme.Checkbox.borderRadius).toBe('3px')
    expect(mowerTheme.Button.borderRadiusSmall).toBe('6px')
    expect(mowerTheme.Input.borderRadius).toBe('8px')
    expect(mowerTheme.Alert.borderRadius).toBe('8px')
    expect(mowerTheme.Popover.borderRadius).toBe('16px')
    expect(mowerTheme.Card.borderRadius).toBe('16px')
  })

  it('keeps tooltip text legible against its floating surface', () => {
    expect(mowerTheme.Tooltip.color).toBe(tooltip.color)
    expect(mowerTheme.Tooltip.textColor).toBe(tooltip.textColor)
    expect(mowerTheme.Tooltip.peers.Popover).toMatchObject(tooltip)
  })

  it('keeps shadows for floating layers while in-page cards stay flat', () => {
    expect(mowerTheme.Card.boxShadow).toBe('none')
    expect(mowerTheme.Modal.boxShadow).not.toBe('none')
    expect(mowerTheme.Drawer.boxShadow).not.toBe('none')
    expect(mowerTheme.Select.menuBoxShadow).not.toBe('none')
    expect(mowerTheme.Popover.boxShadow).not.toBe('none')
  })

  it('derives custom-page semantic colors from the same theme source', () => {
    expect(cssVariables).toMatchObject({
      '--mower-text': mowerTheme.common.textColorBase,
      '--mower-text-muted': mowerTheme.common.textColor3,
      '--mower-surface': mowerTheme.common.cardColor,
      '--mower-shadow-surface': 'none',
      '--mower-shadow-control': 'none',
      '--mower-divider': mowerTheme.common.dividerColor,
      '--mower-primary': mowerTheme.common.primaryColor,
      '--mower-primary-block': mowerTheme.Tag.colorPrimary,
      '--mower-success-text': mowerTheme.Tag.textColorSuccess,
      '--mower-warning-text': mowerTheme.Tag.textColorWarning,
      '--mower-error-text': mowerTheme.Tag.textColorError,
      '--mower-info-text': mowerTheme.Tag.textColorInfo
    })
  })

  it('uses a recessed rail and a contrasting raised capsule for segmented tabs', () => {
    expect(mowerTheme.Tabs.colorSegment).not.toBe(mowerTheme.Tabs.tabColorSegment)
    expect(mowerTheme.Tabs.tabColorSegment).toBe(mowerTheme.common.modalColor)
  })
})
