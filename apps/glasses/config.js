// Where the glasses find Mochi, and whose glasses these are.
//
// backendUrl: the public address of the Mochi backend (MOCHI_PUBLIC_URL),
//   e.g. 'https://mochi.example.com'. Leave it empty to run in demo mode,
//   which replays example suggestions and needs no backend.
// userId: the person wearing the glasses. Suggestions for this person arrive
//   on GET /ws?user=<userId>&surface=ar.
//
// Both can be overridden when the page is opened, without rebuilding:
//   aix launch-page . --params '{"server":"https://...","user":"ben"}'
export default {
  backendUrl: '',
  userId: 'ana',
};
