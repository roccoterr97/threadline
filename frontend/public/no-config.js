// Threadline's shared dashboard has no config.js: the page finds its database
// from the owner's personal link instead. vercel.json answers /config.js with
// this file, so the browser gets a script that does nothing rather than a web
// page it would refuse. A dashboard published by `tracker setup dashboard`
// has a real config.js, which is served before any rule applies.
