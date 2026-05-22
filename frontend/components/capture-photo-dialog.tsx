'use client'

import React, { useRef, useState, useCallback } from 'react'
import Webcam from 'react-webcam'
import {
    Dialog,
    DialogContent,
    DialogHeader,
    DialogTitle,
    DialogDescription,
    DialogFooter
} from "@/components/ui/dialog"
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs"
import { Button } from "@/components/ui/button"
import { Input } from "@/components/ui/input"
import { Camera, RefreshCw, Check, X, Upload, Image as ImageIcon } from 'lucide-react'
import { APIClient } from '@/app/dashboard/lib/api-client'
import { useToast } from "@/hooks/use-toast"

interface CapturePhotoDialogProps {
    isOpen: boolean
    onOpenChange: (open: boolean) => void
    applicationId: number
    onSuccess: () => void
}

export function CapturePhotoDialog({ isOpen, onOpenChange, applicationId, onSuccess }: CapturePhotoDialogProps) {
    const webcamRef = useRef<Webcam>(null)
    const [imgSrc, setImgSrc] = useState<string | null>(null)
    const [isUploading, setIsUploading] = useState(false)
    const [activeTab, setActiveTab] = useState("capture")
    const fileInputRef = useRef<HTMLInputElement>(null)
    const { toast } = useToast()

    const capture = useCallback(() => {
        const imageSrc = webcamRef.current?.getScreenshot()
        setImgSrc(imageSrc || null)
    }, [webcamRef])

    const handleFileUpload = (e: React.ChangeEvent<HTMLInputElement>) => {
        const file = e.target.files?.[0]
        if (file) {
            const reader = new FileReader()
            reader.onloadend = () => {
                setImgSrc(reader.result as string)
            }
            reader.readAsDataURL(file)
        }
    }

    const retake = () => {
        setImgSrc(null)
    }

    const uploadPhoto = async () => {
        if (!imgSrc) return
        
        setIsUploading(true)
        try {
            // Convert base64 to blob
            const response = await fetch(imgSrc)
            const blob = await response.blob()
            
            const formData = new FormData()
            formData.append('photo', blob, 'candidate_photo.jpg')

            await APIClient.postFormData(`/api/onboarding/applications/${applicationId}/capture-photo`, formData)

            toast({ title: "Success", description: "Candidate photo added successfully." })
            onSuccess()
            onOpenChange(false)
            setImgSrc(null)
        } catch (error) {
            toast({ title: "Error", description: "Failed to upload photo", variant: "destructive" })
        } finally {
            setIsUploading(false)
        }
    }

    return (
        <Dialog open={isOpen} onOpenChange={(open) => { onOpenChange(open); if(!open) setImgSrc(null); }}>
            <DialogContent className="sm:max-w-md">
                <DialogHeader>
                    <DialogTitle>Add Candidate Photo</DialogTitle>
                    <DialogDescription>
                        Provide a photo of the candidate for their official ID card.
                    </DialogDescription>
                </DialogHeader>
                
                <Tabs defaultValue="capture" className="w-full" onValueChange={(v) => { setActiveTab(v); setImgSrc(null); }}>
                    <TabsList className="grid w-full grid-cols-2 mb-4">
                        <TabsTrigger value="capture" className="gap-2">
                            <Camera className="h-4 w-4" />
                            Take Photo
                        </TabsTrigger>
                        <TabsTrigger value="upload" className="gap-2">
                            <Upload className="h-4 w-4" />
                            Upload
                        </TabsTrigger>
                    </TabsList>

                    <TabsContent value="capture" className="mt-0">
                        <div className="flex flex-col items-center justify-center bg-slate-900 rounded-xl overflow-hidden aspect-video relative">
                            {!imgSrc ? (
                                <>
                                    <Webcam
                                        audio={false}
                                        ref={webcamRef}
                                        screenshotFormat="image/jpeg"
                                        className="w-full h-full object-cover"
                                        videoConstraints={{ facingMode: "user" }}
                                    />
                                    <div className="absolute bottom-4 left-1/2 -translate-x-1/2">
                                        <Button onClick={capture} variant="secondary" className="rounded-full h-12 w-12 p-0 bg-white/20 hover:bg-white/40 backdrop-blur-md border-white/50 border shadow-lg">
                                            <Camera className="h-6 w-6 text-white" />
                                        </Button>
                                    </div>
                                </>
                            ) : (
                                <>
                                    <img src={imgSrc} className="w-full h-full object-cover" alt="Captured" />
                                    <div className="absolute inset-0 bg-black/40 flex items-center justify-center gap-4 opacity-0 hover:opacity-100 transition-opacity">
                                        <Button onClick={retake} variant="outline" className="bg-white/10 text-white border-white/20">
                                            <RefreshCw className="h-4 w-4 mr-2" />
                                            Retake
                                        </Button>
                                    </div>
                                </>
                            )}
                        </div>
                    </TabsContent>

                    <TabsContent value="upload" className="mt-0">
                        <div className="flex flex-col items-center justify-center border-2 border-dashed border-slate-200 rounded-xl aspect-video bg-slate-50/50 relative overflow-hidden">
                            {!imgSrc ? (
                                <div className="text-center p-6 flex flex-col items-center gap-4">
                                    <div className="p-4 bg-white rounded-full shadow-sm">
                                        <ImageIcon className="h-8 w-8 text-slate-400" />
                                    </div>
                                    <div className="space-y-1">
                                        <p className="text-sm font-semibold text-slate-700">Choose a photo</p>
                                        <p className="text-xs text-slate-500">JPG, PNG or WEBP (Max 5MB)</p>
                                    </div>
                                    <Input 
                                        type="file" 
                                        accept="image/*" 
                                        className="hidden" 
                                        ref={fileInputRef}
                                        onChange={handleFileUpload}
                                    />
                                    <Button 
                                        variant="secondary" 
                                        size="sm"
                                        onClick={() => fileInputRef.current?.click()}
                                    >
                                        Browse Files
                                    </Button>
                                </div>
                            ) : (
                                <>
                                    <img src={imgSrc} className="w-full h-full object-cover" alt="Uploaded" />
                                    <div className="absolute inset-0 bg-black/40 flex items-center justify-center gap-4 opacity-0 hover:opacity-100 transition-opacity">
                                        <Button onClick={retake} variant="outline" className="bg-white/10 text-white border-white/20">
                                            <RefreshCw className="h-4 w-4 mr-2" />
                                            Change Photo
                                        </Button>
                                    </div>
                                </>
                            )}
                        </div>
                    </TabsContent>
                </Tabs>

                <DialogFooter className="sm:justify-between pt-4 border-t">
                    <Button variant="ghost" onClick={() => onOpenChange(false)}>Cancel</Button>
                    {imgSrc && (
                        <Button 
                            onClick={uploadPhoto} 
                            disabled={isUploading}
                            className="bg-emerald-600 hover:bg-emerald-700 font-bold px-8"
                        >
                            {isUploading ? "Uploading..." : `Save ${activeTab === 'capture' ? 'Capture' : 'Upload'}`}
                            {!isUploading && <Check className="ml-2 h-4 w-4" />}
                        </Button>
                    )}
                </DialogFooter>
            </DialogContent>
        </Dialog>
    )
}
