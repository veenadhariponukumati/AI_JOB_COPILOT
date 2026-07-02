import { SignIn } from "@clerk/nextjs";

export default function SignInPage() {
  return (
    <div className="min-h-screen bg-gray-950 flex items-center justify-center">
      <div className="text-center mb-8 absolute top-12">
        <h1 className="text-3xl font-bold text-indigo-400">AI Job Copilot</h1>
        <p className="text-gray-500 text-sm mt-1">ATS resume intelligence platform</p>
      </div>
      <SignIn />
    </div>
  );
}
