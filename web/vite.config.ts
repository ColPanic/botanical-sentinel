import { sveltekit } from '@sveltejs/kit/vite';
import tailwindcss from '@tailwindcss/vite';
import { defineConfig } from 'vite';

export default defineConfig({
	plugins: [tailwindcss(), sveltekit()],
	server: {
		// Allow access by IP as well as hostname (needed when accessing from LAN by IP)
		allowedHosts: true,
		proxy: {
			'/live': { target: 'ws://localhost:8000', ws: true },
			// Proxy REST API routes so the browser can use relative URLs
			// when PUBLIC_API_URL is not set (see src/lib/api.ts)
			'/nodes': 'http://localhost:8000',
			'/devices': 'http://localhost:8000',
			'/scan': 'http://localhost:8000',
			'/positions': 'http://localhost:8000',
			'/health': 'http://localhost:8000',
		},
	},
});
