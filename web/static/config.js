/**
 * SSB WiFi Kiosk - User Configuration
 *
 * Edit this file to customize the kiosk display content.
 * Changes take effect on page reload.
 *
 * Each quadrant can be customized independently:
 * - quadrant1: Top-left (brand/logo)
 * - quadrant2: Top-right (menu)
 * - quadrant3: Bottom-left (promotions)
 * - quadrant4: Bottom-right (QR code - auto-managed)
 */

const KIOSK_CONFIG = {
  // Quadrant 1: Brand/Logo area (top-left)
  quadrant1: {
    title: 'Super Smash Burger',
    subtitle: 'Las mejores hamburguesas de la ciudad',
    // Optional: custom background color/gradient
    // backgroundColor: "linear-gradient(145deg, #ff6b00 0%, #ff8c00 100%)"
  },

  // Quadrant 2: Menu area (top-right)
  quadrant2: {
    title: 'Menu del Dia',
    items: [
      'Smash Classic - $5.500',
      'Smash Doble - $7.500',
      'Smash Bacon - $8.000',
      'Smash Veggie - $6.500',
      'Papas Fritas - $2.500',
      'Bebidas - $1.500',
    ],
    // Optional: custom background
    // backgroundColor: "linear-gradient(145deg, #2d2d2d 0%, #1a1a1a 100%)"
  },

  // Quadrant 3: Promotions area (bottom-left)
  quadrant3: {
    title: 'Promociones',
    promos: [
      { icon: '🍔', text: '2x1 los Martes!' },
      { icon: '🍟', text: 'Combo + Bebida gratis' },
      { icon: '🎉', text: 'Happy Hour 17-19hs' },
      { icon: '💳', text: '10% OFF con MercadoPago' },
    ],
    // Optional: custom background
    // backgroundColor: "linear-gradient(145deg, #1e3a5f 0%, #0d1b2a 100%)"
  },

  // Optional: Custom CSS to inject
  // customCSS: `
  //     .quadrant-1 { font-family: 'Comic Sans MS', cursive; }
  // `
};

/**
 * ADVANCED CUSTOMIZATION
 *
 * To use custom images:
 * 1. Place your images in /opt/ssb-wifi-kiosk/web/static/assets/
 * 2. Reference them in your HTML or CSS as /static/assets/your-image.png
 *
 * To add a custom logo:
 * 1. Save your logo as /opt/ssb-wifi-kiosk/web/static/assets/logo.png
 * 2. The template will automatically display it in quadrant 1
 *
 * For more advanced customization:
 * Edit /opt/ssb-wifi-kiosk/web/templates/index.html directly
 */
