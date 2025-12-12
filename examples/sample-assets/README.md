# Sample Assets

Place your custom images here:

## Logo

- File: `logo.png`
- Recommended size: 200x200 pixels
- Format: PNG with transparency
- Copy to: `/opt/ssb-wifi-kiosk/web/static/assets/logo.png`

## Burger Images (optional)

- Files: `burger1.jpg`, `burger2.jpg`, etc.
- Recommended size: 400x300 pixels
- Format: JPEG or PNG

## Editing the Kiosk Display

Edit `/opt/ssb-wifi-kiosk/web/static/config.js` to customize:

```javascript
const KIOSK_CONFIG = {
  quadrant1: {
    title: 'Your Restaurant Name',
    subtitle: 'Your slogan here',
  },
  quadrant2: {
    title: 'Menu',
    items: [
      'Burger Classic - $8.99',
      'Burger Deluxe - $12.99',
      'Fries - $3.99',
      'Drinks - $2.49',
    ],
  },
  quadrant3: {
    title: "Today's Specials",
    promos: [
      { icon: '🍔', text: '2-for-1 Tuesdays!' },
      { icon: '🎉', text: 'Happy Hour 4-6pm' },
    ],
  },
};
```

## Advanced Customization

For more control, edit the HTML template directly:
`/opt/ssb-wifi-kiosk/web/templates/index.html`

And the CSS:
`/opt/ssb-wifi-kiosk/web/static/style.css`
