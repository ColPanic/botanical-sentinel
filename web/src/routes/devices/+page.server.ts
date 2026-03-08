import { fetchDevices, setDeviceLabel, setDeviceTag } from "$lib/api";
import type { Actions, PageServerLoad } from "./$types";

export const load: PageServerLoad = async ({ url }) => {
  const tag = url.searchParams.get("tag") ?? undefined;
  const devices = await fetchDevices(tag);
  return { devices, activeTag: tag };
};

export const actions: Actions = {
  label: async ({ request }) => {
    const form = await request.formData();
    const mac = String(form.get("mac"));
    const label = String(form.get("label"));
    await setDeviceLabel(mac, label);
    return { success: true };
  },
  tag: async ({ request }) => {
    const form = await request.formData();
    const mac = String(form.get("mac"));
    const tag = String(form.get("tag"));
    await setDeviceTag(mac, tag);
    return { success: true };
  },
};
