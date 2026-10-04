import fs from 'node:fs';

import resolve from '@rollup/plugin-node-resolve';
import commonjs from '@rollup/plugin-commonjs';
import terser from '@rollup/plugin-terser';

import serve from 'rollup-plugin-serve';
import rollupSvelte from 'rollup-plugin-svelte';
import rollupSwc from 'rollup-plugin-swc3';
import rollupCleanup from 'rollup-plugin-cleanup';

import { less } from 'svelte-preprocess-less';
import sveltePreprocess from 'svelte-preprocess';

import { transformCodeToESMPlugin, keyPEM, certificatePEM } from '@windycom/plugin-devtools';

const useSourceMaps = true;

// `set SERVE=false && ...` on Windows leaves a trailing space in the value
const isServing = (process.env.SERVE || '').trim() !== 'false';

const input = 'src/plugin.svelte';
const out = 'plugin';

/** Copies public/mjo.json (written by pipeline/mjo_pipeline.py) next to the bundle for local dev */
const copyDevData = () => ({
    name: 'copy-dev-data',
    writeBundle() {
        if (fs.existsSync('public/mjo.json')) {
            fs.copyFileSync('public/mjo.json', 'dist/mjo.json');
        }
    },
});

export default {
    input,
    output: [
        {
            file: `dist/${out}.js`,
            format: 'module',
            sourcemap: true,
        },
        {
            file: `dist/${out}.min.js`,
            format: 'module',
            plugins: [rollupCleanup({ comments: 'none', extensions: ['ts'] }), terser()],
        },
    ],

    onwarn: () => {
        /* We disable all warning messages */
    },
    external: id => id.startsWith('@windy/'),
    watch: {
        include: ['src/**', 'public/**'],
        exclude: 'node_modules/**',
        clearScreen: false,
    },
    plugins: [
        rollupSvelte({
            emitCss: false,
            preprocess: {
                style: less({
                    sourceMap: false,
                    math: 'always',
                }),
                script: data => {
                    const preprocessed = sveltePreprocess({ sourceMap: useSourceMaps });
                    return preprocessed.script(data);
                },
            },
        }),
        rollupSwc({
            include: ['**/*.ts', '**/*.svelte'],
            sourceMaps: useSourceMaps,
        }),
        resolve({
            browser: true,
            mainFields: ['module', 'jsnext:main', 'main'],
            preferBuiltins: false,
            dedupe: ['svelte'],
        }),
        commonjs(),
        transformCodeToESMPlugin(),
        isServing && copyDevData(),
        isServing &&
            serve({
                contentBase: 'dist',
                host: '0.0.0.0',
                port: 9999,
                headers: {
                    'Access-Control-Allow-Origin': '*',
                },
                https: {
                    key: keyPEM,
                    cert: certificatePEM,
                },
            }),
    ],
};
