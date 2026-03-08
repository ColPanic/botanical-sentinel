import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		allowedHosts: ['blinky'],
		proxy: {
			'/live': { target: 'ws://localhost:8000', ws: true },
		},
	},
});
