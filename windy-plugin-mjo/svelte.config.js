import sveltePreprocess from 'svelte-preprocess';

// Used by editor tooling / svelte-check. The rollup build configures its own preprocessors.
export default {
    preprocess: sveltePreprocess(),
};
