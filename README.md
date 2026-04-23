# PitIQ 🏎️

An F1 race strategy tool that uses machine learning to figure out the best pit stop strategy for a driver.

## The idea

In F1, a lot of races come down to pit strategy. When you pit, what tires you put on, and how that plays out against the cars around you. Top teams have fancy tools for this. PitIQ is my attempt at building a free version of that.

There are two modes I'm building:

**Sandbox mode.** Pick a past race and a driver, drag the pit stops around, and see what your finishing position would have been.

**Optimizer mode.** Pick a driver and a race. The model knows each driver's style (how aggressive they are, how well they save tires, etc.) and simulates the whole grid to figure out the best strategy for them given how everyone else is likely to drive.

## Status

Still building this. Currently working on the data pipeline. Will update as more gets done.