import type { ExternalPluginConfig } from '@windy/interfaces';

const config: ExternalPluginConfig = {
    name: 'windy-plugin-mjo',
    version: '1.0.0',
    icon: '🌀',
    title: 'MJO phase & forecast',
    description:
        'Madden-Julian Oscillation: interactive Wheeler-Hendon RMM phase diagram, current MJO ' +
        'position on the map and the GEFS 31-member ensemble forecast up to 7 days.',
    author: 'Kauswai',
    repository: 'https://github.com/Kauswai/MJO',
    desktopUI: 'rhpane',
    desktopWidth: 440,
    mobileUI: 'fullscreen',
    routerPath: '/mjo-phase',
    private: true,
};

export default config;
