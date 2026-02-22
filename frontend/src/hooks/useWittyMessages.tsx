import { useState, useEffect, useCallback } from 'react'

// Witty loading messages organized by category
const wittyMessages = {
  connecting: [
    "Warming up the neurons...",
    "Establishing quantum entanglement...",
    "Convincing the servers you're important...",
    "Bribing the API gods...",
    "Loading caffeinated hamsters...",
  ],
  thinking: [
    "Contemplating the meaning of your query...",
    "Consulting the oracle...",
    "Running calculations at ludicrous speed...",
    "Teaching AI to read between the lines...",
    "Channeling inner wisdom...",
    "Processing at the speed of thought...",
    "Thinking really hard about this...",
  ],
  fetching: [
    "Rummaging through the data drawers...",
    "Asking nicely for your data...",
    "Herding digital cats...",
    "Retrieving ancient scrolls of knowledge...",
    "Mining for golden insights...",
    "Interrogating the database...",
    "Convincing data to come out of hiding...",
    "Fetching... like a very smart dog...",
  ],
  analyzing: [
    "Crunching numbers with gusto...",
    "Separating signal from noise...",
    "Finding patterns in the chaos...",
    "Applying 10,000 hours of expertise...",
    "Reading between the bytes...",
    "Performing data archaeology...",
    "Synthesizing brilliance...",
  ],
  almost_done: [
    "Almost there... probably...",
    "Putting on the finishing touches...",
    "Triple-checking for typos...",
    "Making it look pretty...",
    "99% done (the hard 99%)...",
    "Polishing the response...",
  ]
}

type MessageCategory = keyof typeof wittyMessages

export function useWittyMessages(
  isActive: boolean,
  category: MessageCategory = 'thinking',
  intervalMs: number = 2500
) {
  const [currentIndex, setCurrentIndex] = useState(0)
  const messages = wittyMessages[category]

  useEffect(() => {
    if (!isActive) {
      setCurrentIndex(0)
      return
    }

    // Start with a random message
    setCurrentIndex(Math.floor(Math.random() * messages.length))

    const interval = setInterval(() => {
      setCurrentIndex(prev => (prev + 1) % messages.length)
    }, intervalMs)

    return () => clearInterval(interval)
  }, [isActive, category, messages.length, intervalMs])

  return messages[currentIndex]
}

// Simpler hook that cycles through all categories based on elapsed time
export function useSmartWittyMessage(isActive: boolean, elapsedMs: number = 0) {
  const [message, setMessage] = useState('')

  const getCategory = useCallback((elapsed: number): MessageCategory => {
    if (elapsed < 1000) return 'connecting'
    if (elapsed < 5000) return 'fetching'
    if (elapsed < 15000) return 'thinking'
    if (elapsed < 30000) return 'analyzing'
    return 'almost_done'
  }, [])

  useEffect(() => {
    if (!isActive) {
      setMessage('')
      return
    }

    const updateMessage = () => {
      const category = getCategory(elapsedMs)
      const messages = wittyMessages[category]
      const randomMessage = messages[Math.floor(Math.random() * messages.length)]
      setMessage(randomMessage)
    }

    updateMessage()
    const interval = setInterval(updateMessage, 2500)

    return () => clearInterval(interval)
  }, [isActive, elapsedMs, getCategory])

  return message
}

// Simple rotating message component
export function RotatingMessage({
  isActive,
  category = 'thinking'
}: {
  isActive: boolean
  category?: MessageCategory
}) {
  const message = useWittyMessages(isActive, category)

  if (!isActive) return null

  return (
    <span className="inline-block transition-opacity duration-300">
      {message}
    </span>
  )
}

export default useWittyMessages
