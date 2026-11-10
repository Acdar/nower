import { darkTheme, lightTheme } from 'naive-ui'

const transparentBorder = '1px solid transparent'

const sharedCommon = {
  borderRadius: '8px',
  borderRadiusSmall: '6px',
  fontWeightStrong: '600',
  // 明暗两套色板的大投影相同，只在这里写一次
  boxShadow3:
    '0 6px 16px -9px rgba(0, 0, 0, .08), 0 9px 28px 0 rgba(0, 0, 0, .05), 0 12px 48px 16px rgba(0, 0, 0, .03)'
}

function createMowerTheme(palette) {
  // shadcn `outline` 变体的默认按钮：给普通（无 type）按钮 1px 可见边框，
  // 让它不再是无边框的浅灰平铺块。primary 系列保留透明边框（实心绿不要边）。
  const defaultBorder = `1px solid ${palette.border}`
  return {
    common: {
      ...sharedCommon,
      textColorBase: palette.textBase,
      textColor1: palette.text1,
      textColor2: palette.text2,
      textColor3: palette.text3,
      primaryColor: palette.primary,
      primaryColorHover: palette.primaryHover,
      primaryColorPressed: palette.primaryPressed,
      primaryColorSuppl: palette.primarySuppl,
      successColor: palette.success,
      successColorHover: palette.successHover,
      successColorPressed: palette.successPressed,
      successColorSuppl: palette.successSuppl,
      warningColor: palette.warning,
      warningColorHover: palette.warningHover,
      warningColorPressed: palette.warningPressed,
      warningColorSuppl: palette.warningSuppl,
      errorColor: palette.error,
      errorColorHover: palette.errorHover,
      errorColorPressed: palette.errorPressed,
      errorColorSuppl: palette.errorSuppl,
      infoColor: palette.info,
      infoColorHover: palette.infoHover,
      infoColorPressed: palette.infoPressed,
      infoColorSuppl: palette.infoSuppl,
      bodyColor: palette.page,
      cardColor: palette.surface,
      modalColor: palette.surfaceRaised,
      popoverColor: palette.popover,
      inputColor: palette.input,
      actionColor: palette.control,
      hoverColor: palette.controlHover,
      pressedColor: palette.controlPressed,
      borderColor: palette.border,
      dividerColor: palette.divider,
      tableColor: palette.surface,
      tableHeaderColor: palette.tableHeader,
      tableColorStriped: palette.tableStriped,
      tabColor: palette.tab,
      boxShadow1: palette.shadowSmall,
      boxShadow2: palette.shadowMedium
    },
    Layout: {
      color: palette.page,
      colorEmbedded: palette.control,
      headerColor: palette.surface,
      siderColor: palette.sider,
      footerColor: palette.surface,
      headerBorderColor: 'transparent',
      siderBorderColor: 'transparent',
      footerBorderColor: 'transparent'
    },
    Button: {
      borderRadiusTiny: '4px',
      borderRadiusSmall: '6px',
      borderRadiusMedium: '8px',
      borderRadiusLarge: '10px',
      border: defaultBorder,
      borderFocus: defaultBorder,
      borderHover: defaultBorder,
      borderPressed: defaultBorder,
      borderDisabled: defaultBorder,
      color: palette.control,
      colorFocus: palette.controlHover,
      colorHover: palette.controlHover,
      colorPressed: palette.controlPressed,
      borderPrimary: transparentBorder,
      borderFocusPrimary: transparentBorder,
      borderHoverPrimary: transparentBorder,
      borderPressedPrimary: transparentBorder,
      colorPrimary: palette.accent,
      colorFocusPrimary: palette.accentHover,
      colorHoverPrimary: palette.accentHover,
      colorPressedPrimary: palette.accentPressed,
      rippleColorPrimary: palette.accentPressed,
      textColorPrimary: palette.accentText,
      textColorFocusPrimary: palette.accentText,
      textColorHoverPrimary: palette.accentText,
      textColorPressedPrimary: palette.accentText
    },
    Card: {
      color: palette.cardBlock,
      colorEmbedded: palette.control,
      actionColor: palette.control,
      borderColor: 'transparent',
      borderRadius: '16px',
      closeBorderRadius: '6px',
      boxShadow: 'none'
    },
    Dialog: {
      border: transparentBorder,
      borderRadius: '16px',
      closeBorderRadius: '6px',
      color: palette.surfaceRaised
    },
    Modal: {
      boxShadow: sharedCommon.boxShadow3
    },
    Drawer: {
      borderRadius: '16px',
      closeBorderRadius: '6px',
      boxShadow: sharedCommon.boxShadow3
    },
    Input: {
      border: transparentBorder,
      borderDisabled: transparentBorder,
      borderFocus: transparentBorder,
      borderHover: transparentBorder,
      borderRadius: '8px',
      boxShadowFocus: palette.focusShadow,
      color: palette.control,
      colorDisabled: palette.controlDisabled,
      colorFocus: palette.controlFocus,
      caretColor: palette.primary
    },
    Checkbox: {
      // 复选框填充是近乎白色的控件色，和卡片几乎没有对比，只有一档最轻的可见描边
      // （与普通按钮同一档）才立得住边界。五个状态给同一圈描边：naive-ui 的悬停规则
      // 取的是 borderChecked，勾选态若留透明描边，鼠标移上去描边会突然消失。
      border: defaultBorder,
      borderChecked: defaultBorder,
      borderDisabled: defaultBorder,
      borderDisabledChecked: defaultBorder,
      borderFocus: defaultBorder,
      boxShadowFocus: palette.focusShadow,
      borderRadius: '3px',
      color: palette.control,
      colorChecked: palette.accent,
      colorDisabled: palette.controlDisabled,
      colorDisabledChecked: palette.controlDisabled,
      checkMarkColor: palette.accentText
    },
    Radio: {
      buttonBorderRadius: '6px',
      color: palette.control,
      colorActive: palette.accent,
      dotColorActive: palette.accentText,
      boxShadow: `inset 0 0 0 1px ${palette.border}`,
      boxShadowHover: `inset 0 0 0 1px ${palette.primary}`,
      boxShadowActive: 'none',
      boxShadowFocus: palette.focusShadow
    },
    Switch: {
      railBorderRadiusSmall: '9px',
      railBorderRadiusMedium: '11px',
      railBorderRadiusLarge: '13px',
      buttonBorderRadiusSmall: '7px',
      buttonBorderRadiusMedium: '9px',
      buttonBorderRadiusLarge: '11px',
      railColor: palette.controlPressed,
      railColorActive: palette.accent,
      buttonColor: palette.surfaceRaised,
      buttonBoxShadow: 'none',
      boxShadowFocus: palette.focusShadow,
      textColor: palette.accentText
    },
    Select: {
      menuBoxShadow: palette.shadowMedium,
      peers: {
        InternalSelectMenu: {
          borderRadius: '12px',
          color: palette.popover,
          optionColorPending: palette.controlHover,
          optionColorActive: 'transparent',
          optionColorActivePending: palette.controlHover
        }
      }
    },
    AutoComplete: {
      menuBoxShadow: palette.shadowMedium
    },
    Tag: {
      border: transparentBorder,
      borderPrimary: transparentBorder,
      borderSuccess: transparentBorder,
      borderWarning: transparentBorder,
      borderError: transparentBorder,
      borderInfo: transparentBorder,
      borderRadius: '3px',
      closeBorderRadius: '3px',
      color: palette.control,
      colorBordered: palette.control,
      colorPrimary: palette.primaryBlock,
      colorBorderedPrimary: palette.primaryBlock,
      colorSuccess: palette.successBlock,
      colorBorderedSuccess: palette.successBlock,
      colorWarning: palette.warningBlock,
      colorBorderedWarning: palette.warningBlock,
      colorError: palette.errorBlock,
      colorBorderedError: palette.errorBlock,
      colorInfo: palette.infoBlock,
      colorBorderedInfo: palette.infoBlock,
      textColorPrimary: palette.primaryText,
      textColorSuccess: palette.successText,
      textColorWarning: palette.warningText,
      textColorError: palette.errorText,
      textColorInfo: palette.infoText
    },
    Popover: {
      color: palette.popover,
      borderRadius: '16px',
      boxShadow: palette.shadowMedium
    },
    Dropdown: {
      borderRadius: '12px',
      color: palette.popover,
      dividerColor: palette.divider
    },
    Tooltip: {
      borderRadius: '6px',
      boxShadow: palette.shadowSmall,
      color: palette.tooltip,
      textColor: palette.tooltipText,
      peers: {
        Popover: {
          borderRadius: '6px',
          boxShadow: palette.shadowSmall,
          color: palette.tooltip,
          textColor: palette.tooltipText
        }
      }
    },
    Message: {
      borderRadius: '8px',
      closeBorderRadius: '5px',
      boxShadow: palette.shadowMedium,
      boxShadowInfo: palette.shadowMedium,
      boxShadowSuccess: palette.shadowMedium,
      boxShadowWarning: palette.shadowMedium,
      boxShadowError: palette.shadowMedium,
      boxShadowLoading: palette.shadowMedium
    },
    Notification: {
      borderRadius: '14px',
      closeBorderRadius: '5px',
      boxShadow: palette.shadowMedium
    },
    Alert: {
      border: transparentBorder,
      borderInfo: transparentBorder,
      borderSuccess: transparentBorder,
      borderWarning: transparentBorder,
      borderError: transparentBorder,
      borderRadius: '8px',
      closeBorderRadius: '5px',
      color: palette.control,
      colorInfo: palette.alertInfoBlock,
      colorSuccess: palette.alertSuccessBlock,
      colorWarning: palette.alertWarningBlock,
      colorError: palette.alertErrorBlock,
      iconColorInfo: palette.alertInfoIcon,
      iconColorSuccess: palette.alertSuccessIcon,
      iconColorWarning: palette.alertWarningIcon,
      iconColorError: palette.alertErrorIcon
    },
    Divider: {
      color: palette.divider
    },
    Collapse: {
      dividerColor: 'transparent',
      titleFontWeight: '600'
    },
    DataTable: {
      borderRadius: '10px',
      borderColor: palette.divider,
      thColor: palette.tableHeader,
      tdColor: palette.surface,
      tdColorStriped: palette.tableStriped
    },
    DatePicker: {
      itemBorderRadius: '4px',
      scrollItemBorderRadius: '4px',
      panelBorderRadius: '10px',
      panelBoxShadow: palette.shadowMedium,
      panelColor: palette.surfaceRaised,
      panelHeaderDividerColor: palette.divider,
      calendarDaysDividerColor: palette.divider,
      calendarDividerColor: palette.divider,
      panelActionDividerColor: palette.divider
    },
    List: {
      borderRadius: '10px',
      borderColor: palette.divider,
      color: palette.surface,
      colorHover: palette.controlHover
    },
    Slider: {
      /* 亮色下白色 thumb 会融进白色轨道/背景，给一圈极淡描边+柔和投影分离轮廓（不改颜色） */
      handleBoxShadow: '0 0 0 1px rgba(0, 0, 0, 0.12), 0 1px 3px rgba(0, 0, 0, 0.14)',
      handleBoxShadowFocus: palette.focusShadow,
      indicatorBorderRadius: '6px',
      indicatorBoxShadow: palette.shadowSmall
    },
    Table: {
      borderRadius: '10px',
      borderColor: palette.divider,
      thColor: palette.tableHeader,
      tdColor: palette.surface,
      tdColorStriped: palette.tableStriped
    },
    Tabs: {
      tabBorderRadius: '8px',
      closeBorderRadius: '4px',
      tabColor: palette.control,
      tabColorSegment: palette.surfaceRaised,
      colorSegment: palette.controlPressed
    },
    TimePicker: {
      itemBorderRadius: '4px',
      borderRadius: '10px',
      panelBoxShadow: palette.shadowMedium,
      panelColor: palette.surfaceRaised,
      panelDividerColor: palette.divider
    },
    Upload: {
      borderRadius: '8px',
      draggerColor: palette.control,
      draggerBorder: transparentBorder,
      draggerBorderHover: transparentBorder,
      itemColorHover: palette.controlHover
    }
  }
}

export const mowerLightThemeOverrides = createMowerTheme({
  textBase: '#2a303c',
  text1: '#2a303c',
  text2: '#434c5e',
  text3: '#6c768a',
  primary: '#3e4656',
  primaryHover: '#4f596d',
  primaryPressed: '#2e3440',
  primarySuppl: '#4f596d',
  accent: '#3e4656',
  accentHover: '#4f596d',
  accentPressed: '#2e3440',
  accentText: '#ffffff',
  success: '#2e7d5b',
  successHover: '#3f916d',
  successPressed: '#216346',
  successSuppl: '#3f916d',
  warning: '#c47222',
  warningHover: '#d68534',
  warningPressed: '#a35b14',
  warningSuppl: '#d68534',
  error: '#c93850',
  errorHover: '#d94e65',
  errorPressed: '#a8283e',
  errorSuppl: '#d94e65',
  info: '#4c73a8',
  infoHover: '#6088bd',
  infoPressed: '#3a5d8c',
  infoSuppl: '#6088bd',
  page: '#f5f7fb',
  surface: '#fafbfd',
  surfaceRaised: '#ffffff',
  popover: '#ffffff',
  tooltip: 'rgba(42, 48, 60, 0.92)',
  tooltipText: '#f5f7fb',
  input: '#ffffff',
  sider: '#eaeff6',
  cardBlock: '#fafbfd',
  control: '#edf1f7',
  controlHover: '#e3e9f2',
  controlPressed: '#d8dfea',
  controlFocus: '#ffffff',
  controlDisabled: '#edf1f7',
  border: '#d8dfea',
  divider: '#e5ebf3',
  tableHeader: '#edf1f7',
  tableStriped: 'rgba(62, 70, 86, 0.03)',
  tab: '#e6ecf4',
  primaryBlock: 'rgba(62, 70, 86, 0.12)',
  primaryText: '#2e3440',
  successBlock: 'rgba(46, 125, 91, 0.13)',
  successText: '#216346',
  warningBlock: 'rgba(196, 114, 34, 0.14)',
  warningText: '#a35b14',
  errorBlock: 'rgba(201, 56, 80, 0.12)',
  errorText: '#a8283e',
  infoBlock: 'rgba(76, 115, 168, 0.13)',
  infoText: '#3a5d8c',
  alertInfoBlock: 'rgba(235, 242, 250, 1)',
  alertSuccessBlock: 'rgba(234, 245, 240, 1)',
  alertWarningBlock: 'rgba(251, 242, 229, 1)',
  alertErrorBlock: 'rgba(251, 235, 238, 1)',
  alertInfoIcon: '#4c73a8',
  alertSuccessIcon: '#2e7d5b',
  alertWarningIcon: '#c47222',
  alertErrorIcon: '#c93850',
  focusShadow: '0 0 0 2px rgba(78, 100, 142, 0.24)',
  switchShadow: '0 1px 3px rgba(42, 48, 60, 0.14)',
  shadowSmall:
    '0 1px 2px -2px rgba(42, 48, 60, .10), 0 3px 6px 0 rgba(42, 48, 60, .07), 0 5px 12px 4px rgba(42, 48, 60, .05)',
  shadowMedium:
    '0 3px 6px -4px rgba(42, 48, 60, .14), 0 6px 16px 0 rgba(42, 48, 60, .09), 0 9px 28px 8px rgba(42, 48, 60, .06)'
})

export const mowerDarkThemeOverrides = createMowerTheme({
  textBase: '#eceff4',
  text1: '#eceff4',
  text2: '#d8dee9',
  text3: '#949cb0',
  primary: '#88c0d0',
  primaryHover: '#8fbcbb',
  primaryPressed: '#81a1c1',
  primarySuppl: '#5e81ac',
  accent: '#88c0d0',
  accentHover: '#8fbcbb',
  accentPressed: '#81a1c1',
  accentText: '#272935',
  success: '#a3be8c',
  successHover: '#b5cca1',
  successPressed: '#8fa978',
  successSuppl: '#6d8a56',
  warning: '#ebcb8b',
  warningHover: '#f0d7a3',
  warningPressed: '#d8b774',
  warningSuppl: '#d08770',
  error: '#d07079',
  errorHover: '#dc848c',
  errorPressed: '#bf616a',
  errorSuppl: '#bf616a',
  info: '#81a1c1',
  infoHover: '#88c0d0',
  infoPressed: '#5e81ac',
  infoSuppl: '#5e81ac',
  page: '#2b2e3b',
  surface: '#363b4c',
  surfaceRaised: '#404659',
  popover: '#404659',
  tooltip: '#4a5268',
  tooltipText: '#eceff4',
  input: 'rgba(236, 239, 244, 0.08)',
  sider: '#252834',
  cardBlock: '#363b4c',
  control: 'rgba(236, 239, 244, 0.07)',
  controlHover: 'rgba(236, 239, 244, 0.11)',
  controlPressed: 'rgba(236, 239, 244, 0.05)',
  controlFocus: 'rgba(236, 239, 244, 0.12)',
  controlDisabled: 'rgba(236, 239, 244, 0.05)',
  border: 'rgba(216, 222, 233, 0.2)',
  divider: 'rgba(216, 222, 233, 0.1)',
  tableHeader: 'rgba(236, 239, 244, 0.06)',
  tableStriped: 'rgba(236, 239, 244, 0.04)',
  tab: 'rgba(37, 40, 52, 0.55)',
  primaryBlock: 'rgba(136, 192, 208, 0.16)',
  primaryText: '#88c0d0',
  successBlock: 'rgba(163, 190, 140, 0.16)',
  successText: '#a3be8c',
  warningBlock: 'rgba(235, 203, 139, 0.16)',
  warningText: '#ebcb8b',
  errorBlock: 'rgba(208, 112, 121, 0.18)',
  errorText: '#e28c96',
  infoBlock: 'rgba(129, 161, 193, 0.18)',
  infoText: '#88c0d0',
  alertInfoBlock: 'rgba(94, 129, 172, 0.25)',
  alertSuccessBlock: 'rgba(163, 190, 140, 0.22)',
  alertWarningBlock: 'rgba(208, 135, 112, 0.24)',
  alertErrorBlock: 'rgba(191, 97, 106, 0.26)',
  alertInfoIcon: '#88c0d0',
  alertSuccessIcon: '#a3be8c',
  alertWarningIcon: '#ebcb8b',
  alertErrorIcon: '#e28c96',
  focusShadow: '0 0 0 2px rgba(136, 192, 208, 0.24)',
  switchShadow: '0 1px 3px rgba(0, 0, 0, 0.28)',
  shadowSmall:
    '0 1px 2px -2px rgba(18, 20, 28, .32), 0 3px 6px 0 rgba(18, 20, 28, .24), 0 5px 12px 4px rgba(18, 20, 28, .16)',
  shadowMedium:
    '0 3px 6px -4px rgba(18, 20, 28, .32), 0 6px 12px 0 rgba(18, 20, 28, .22), 0 9px 18px 8px rgba(18, 20, 28, .14)'
})

function createMowerCssVariables(theme, defaults) {
  return {
    '--mower-text': theme.common.textColorBase ?? defaults.textColorBase,
    '--mower-text-muted': theme.common.textColor3 ?? defaults.textColor3,
    '--mower-border': theme.common.borderColor,
    '--mower-surface': theme.common.cardColor,
    '--mower-sidebar-surface': theme.Layout.siderColor,
    '--mower-shadow-surface': 'none',
    '--mower-shadow-control': 'none',
    '--mower-control-surface': theme.common.actionColor,
    '--mower-control-hover': theme.common.hoverColor,
    '--mower-divider': theme.common.dividerColor,
    '--mower-primary': theme.common.primaryColor,
    '--mower-primary-hover': theme.common.primaryColorHover,
    '--mower-primary-contrast': theme.Button.textColorPrimary,
    '--mower-primary-block': theme.Tag.colorPrimary,
    '--mower-primary-text': theme.Tag.textColorPrimary,
    '--mower-success': theme.common.successColor,
    '--mower-success-block': theme.Tag.colorSuccess,
    '--mower-success-text': theme.Tag.textColorSuccess,
    '--mower-warning': theme.common.warningColor,
    '--mower-warning-block': theme.Tag.colorWarning,
    '--mower-warning-text': theme.Tag.textColorWarning,
    '--mower-error': theme.common.errorColor,
    '--mower-error-block': theme.Tag.colorError,
    '--mower-error-text': theme.Tag.textColorError,
    '--mower-info': theme.common.infoColor,
    '--mower-info-block': theme.Tag.colorInfo,
    '--mower-info-text': theme.Tag.textColorInfo
  }
}

export const mowerLightCssVariables = createMowerCssVariables(
  mowerLightThemeOverrides,
  lightTheme.common
)
export const mowerDarkCssVariables = createMowerCssVariables(
  mowerDarkThemeOverrides,
  darkTheme.common
)
