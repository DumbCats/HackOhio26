import "dotenv/config";
import { Spectrum } from "spectrum-ts";
import { imessage } from "@spectrum-ts/imessage";

console.log("Connecting to Spectrum Cloud for iMessage...");

const app = await Spectrum({
  projectId: process.env.PROJECT_ID!,
  projectSecret: process.env.PROJECT_SECRET!,
  providers: [
    imessage.config(),
  ],
});

console.log("Spectrum connected and listening for incoming iMessages!");

for await (const [space, message] of app.messages) {
  const senderId = message.sender?.id || "unknown sender";
  console.log(`[+] Received message from ${senderId}:`, message.content);

  if (message.content.type === "text") {
    const text = message.content.text;
    console.log(`[+] Sending echo reply: echo: ${text}`);
    await space.send(`echo: ${text}`);
    console.log(`[?] Reply dispatched!`);
  }
}

